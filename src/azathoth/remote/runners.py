"""The runners that run a remote's jobs, on threads of the server that serves it (ADR 0138).

`JobRunners` starts a number of runners, each a thread that claims the job
waiting longest and runs it through its caller's own instance, so what it
makes is the caller's, telling each event into the job's events as it is
told. One more thread watches them: it asks a running job to stop once its
cancellation is asked for, beats for every runner, and recovers the jobs of
runners that stopped beating, on this server or on another over the same
PostgreSQL database.

A stalled job that can go on from where it was is queued again: a resumed
run or invocation resumes again, and an invocation is invoked again under
its idempotency key, which resumes it. Any other is interrupted, since
nothing resumes a benchmark, an optimization, a step tried or a run whose
ID was not yet known. A server that stops hands its running jobs back the
same way, at once.
"""

import json
import logging
import os
import socket
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from types import TracebackType
from typing import Final
from uuid import UUID

from azathoth.api.errors import ApiError, RunCancelledError
from azathoth.api.running import CancellationToken
from azathoth.remote.calling import CallerInstances, job_signature
from azathoth.remote.jobs import (
    DEFAULT_RUNNERS,
    RUNNER_ALIVE_SECONDS,
    ServiceJob,
    ServiceJobRepository,
    ServiceJobStatus,
)
from azathoth.remote.refusals import refusal_body
from azathoth.remote.service import api_error_status

LOGGER: Final = logging.getLogger(__name__)

POLL_SECONDS: Final = 1.0
"""How often an idle runner looks for a job, and a running job's cancellation is checked."""

BEAT_SECONDS: Final = 10.0
"""How often every runner beats."""

STALL_SECONDS: Final = RUNNER_ALIVE_SECONDS
"""How long a runner may go without beating before its jobs are recovered."""

INTERRUPTED_CODE: Final = "interrupted"
"""The code a job interrupted by a server that stopped is refused with."""

FAILED_CODE: Final = "error"
"""The code a job that failed in a way the service API does not name is refused with."""

RESUMED_AS_SUBMITTED: Final = frozenset({"runs.resume", "invocations.resume", "runs.invoke"})
"""The jobs that go on from where they were when they are run again as they were submitted.

A resume continues its run's journal. An invocation is keyed, so invoking it
again under its key resumes it rather than starting anew.
"""


def interrupted_message(
    call: str,
) -> str:
    """Return what a job interrupted by a server that stopped says, by its call."""

    if call == "runs.run":
        return (
            "The server running this job stopped before it finished. A run it started is "
            "named by runs.interrupted, and runs.resume resumes it from its journal."
        )

    return (
        f"The server running this job stopped before it finished, and nothing resumes "
        f"{call}; submit it again."
    )


def failed_message(
    call: str,
) -> str:
    """Return what a job that failed in a way the service API does not name says."""

    return f"{call} failed at the remote; its log says why."


@dataclass
class _Held:
    """A job a runner holds: its token, and whether its server is stopping."""

    runner_id: str
    token: CancellationToken = field(default_factory=CancellationToken)
    stopping: bool = False


class JobRunners:
    """The runners of one server, and the thread that watches them.

    Start them, best as a context manager, and stop them when the server
    stops: stopping asks every running job to stop, and hands each back to
    be recovered, then forgets the runners.
    """

    def __init__(
        self,
        jobs: ServiceJobRepository,
        instances: CallerInstances,
        *,
        count: int = DEFAULT_RUNNERS,
        server: str | None = None,
        poll_seconds: float = POLL_SECONDS,
        beat_seconds: float = BEAT_SECONDS,
        stall_seconds: float = STALL_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Run `count` jobs at once, from `jobs`, each as its caller's instance from `instances`.

        Raises:
            ValueError: The count is below 1.
        """

        if count < 1:
            raise ValueError("A server runs at least one job at once, or no runners at all.")

        self._jobs = jobs
        self._instances = instances
        self._count = count
        self._server = server if server is not None else f"{socket.gethostname()} pid {os.getpid()}"
        self._poll_seconds = poll_seconds
        self._beat_seconds = beat_seconds
        self._stall_seconds = stall_seconds
        self._clock = clock
        self._stopping = threading.Event()
        self._held: dict[UUID, _Held] = {}
        self._lock = threading.Lock()
        self._runner_ids: tuple[str, ...] = ()
        self._threads: list[threading.Thread] = []

    def __enter__(
        self,
    ) -> "JobRunners":
        self.start()

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    @property
    def runner_ids(
        self,
    ) -> tuple[str, ...]:
        """Return the IDs of this server's runners, once started."""

        return self._runner_ids

    @property
    def running(
        self,
    ) -> frozenset[UUID]:
        """Return the jobs this server's runners hold now."""

        with self._lock:
            return frozenset(self._held)

    def start(
        self,
    ) -> None:
        """Record the runners, and start them and the thread that watches them.

        Raises:
            RuntimeError: The runners were already started.
        """

        if self._threads:
            raise RuntimeError("These runners were already started.")

        self._runner_ids = tuple(f"runner-{uuid.uuid4()}" for _ in range(self._count))

        for runner_id in self._runner_ids:
            self._jobs.register_runner(runner_id, self._server)

        self._threads = [
            threading.Thread(target=self._run, args=(runner_id,), name=runner_id, daemon=True)
            for runner_id in self._runner_ids
        ]
        self._threads.append(
            threading.Thread(target=self._watch, name="job-runners-watch", daemon=True)
        )

        for thread in self._threads:
            thread.start()

    def stop(
        self,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Ask every running job to stop, wait for the runners, and forget them.

        A job stopped this way is handed back as a stalled one is recovered,
        unless its caller had asked it to stop, when it ends cancelled.
        """

        self._stopping.set()

        with self._lock:
            for held in self._held.values():
                held.stopping = True
                held.token.cancel()

        for thread in self._threads:
            thread.join(timeout_seconds)

        for runner_id in self._runner_ids:
            self._jobs.retire_runner(runner_id)

    def recover(
        self,
    ) -> int:
        """Recover every job whose runner stopped beating, and return how many were.

        A job another server recovered first is left to it.
        """

        before = self._clock() - timedelta(seconds=self._stall_seconds)
        recovered = 0

        for stalled in self._jobs.stalled(before):
            if self._hand_back(stalled):
                recovered += 1

        return recovered

    def _run(
        self,
        runner_id: str,
    ) -> None:
        """Run one job after another until the server stops."""

        while not self._stopping.is_set():
            try:
                job = self._jobs.claim(runner_id)
            except Exception:
                LOGGER.exception("Runner %s could not claim a job.", runner_id)
                job = None

            if job is None:
                self._stopping.wait(self._poll_seconds)
                continue

            self._execute(runner_id, job)

    def _execute(
        self,
        runner_id: str,
        job: ServiceJob,
    ) -> None:
        """Run one job its runner claimed, and end it as it ended."""

        held = _Held(runner_id=runner_id)

        with self._lock:
            self._held[job.job_id] = held

            if self._stopping.is_set():
                held.stopping = True
                held.token.cancel()

        try:
            self._outcome(job, held)
        except Exception:
            LOGGER.exception("Job %s could not be ended as it ended.", job.job_id)
        finally:
            with self._lock:
                self._held.pop(job.job_id, None)

    def _outcome(
        self,
        job: ServiceJob,
        held: _Held,
    ) -> None:
        """Run a job's call and record how it ended."""

        signature = job_signature(job.call)

        def told(
            event: object,
        ) -> None:
            self._jobs.append_event(job.job_id, signature.write_event(event).decode())

        try:
            instance = self._instances.instance(job.principal)
            arguments = signature.read_arguments(job.arguments.encode())
            result = signature.bound(instance)(**arguments, on_event=told, cancel=held.token)
        except RunCancelledError as error:
            if held.stopping and not self._cancel_asked(job.job_id):
                current = self._jobs.get(job.job_id)

                if current is not None:
                    self._hand_back(current)

                return

            self._finish(job, held, ServiceJobStatus.CANCELLED, error=error)
        except ApiError as error:
            self._finish(job, held, ServiceJobStatus.FAILED, error=error)
        except Exception:
            LOGGER.exception("Job %s of %s failed.", job.job_id, job.call)
            self._jobs.finish(
                job.job_id,
                held.runner_id,
                ServiceJobStatus.FAILED,
                refusal=json.dumps({"error": failed_message(job.call), "code": FAILED_CODE}),
                refusal_status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        else:
            self._jobs.finish(
                job.job_id,
                held.runner_id,
                ServiceJobStatus.SUCCEEDED,
                result=signature.write_result(result).decode(),
            )

    def _finish(
        self,
        job: ServiceJob,
        held: _Held,
        status: ServiceJobStatus,
        *,
        error: ApiError,
    ) -> None:
        """End a job with the refusal its error is answered with."""

        self._jobs.finish(
            job.job_id,
            held.runner_id,
            status,
            refusal=json.dumps(refusal_body(error)),
            refusal_status=api_error_status(error),
        )

    def _cancel_asked(
        self,
        job_id: UUID,
    ) -> bool:
        """Return whether a job's caller, or another, asked it to stop."""

        current = self._jobs.get(job_id)

        return current is not None and current.cancel_requested_at is not None

    def _hand_back(
        self,
        stalled: ServiceJob,
    ) -> bool:
        """Queue a job again to go on from where it was, or interrupt it; return whether it was."""

        if stalled.call in RESUMED_AS_SUBMITTED:
            return self._jobs.requeue(stalled, call=stalled.call, arguments=stalled.arguments)

        refusal = {"error": interrupted_message(stalled.call), "code": INTERRUPTED_CODE}

        return self._jobs.interrupt(
            stalled,
            refusal=json.dumps(refusal),
            refusal_status=HTTPStatus.CONFLICT,
        )

    def _watch(
        self,
    ) -> None:
        """Ask jobs to stop when asked, beat for every runner, and recover stalled jobs."""

        last_beat = self._clock()

        while not self._stopping.wait(self._poll_seconds):
            try:
                self._pass_on_cancellations()

                if (self._clock() - last_beat).total_seconds() >= self._beat_seconds:
                    last_beat = self._clock()

                    for runner_id in self._runner_ids:
                        self._jobs.beat(runner_id)

                    self.recover()
            except Exception:
                LOGGER.exception("The runners' watch could not keep watch.")

    def _pass_on_cancellations(
        self,
    ) -> None:
        """Cancel the token of every running job whose caller asked it to stop."""

        with self._lock:
            held = dict(self._held)

        for job_id, holding in held.items():
            if not holding.token.cancelled and self._cancel_asked(job_id):
                holding.token.cancel()


__all__ = [
    "BEAT_SECONDS",
    "DEFAULT_RUNNERS",
    "FAILED_CODE",
    "INTERRUPTED_CODE",
    "POLL_SECONDS",
    "RESUMED_AS_SUBMITTED",
    "STALL_SECONDS",
    "JobRunners",
    "failed_message",
    "interrupted_message",
]

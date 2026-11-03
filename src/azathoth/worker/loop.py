"""The queue worker's loop: receive, run, settle, extend, drain (ADR 0107).

A worker takes one message at a time from a job queue, and runs it with a
handler, which answers the job request its body carries with a job result
(ADR 0097). The result settles the message:

- `succeeded`, `failed` and `rejected` are final: the result is sent to the
  result queue, when there is one, and the message is deleted;
- `incomplete` means another process holds the run: the message is left, and
  comes back when its visibility timeout runs out.

While a job runs, the message's visibility is extended, so it is not
delivered again under a live run. When the worker is told to stop, it stops
receiving, cancels the job it is running, which releases the run's lease as
it unwinds, and hands the message back to the queue at once, so another
worker resumes the run from its journal (ADR 0105).

A handler never raises for a request's own problems; those are results. A
handler that raises means the worker cannot run jobs at all, so the message
is left and the worker stops with the error.
"""

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.jobs import JobResult, JobStatus, readable_idempotency_key
from azathoth.worker.queue import JobQueue, QueueMessage, ResultQueue

DEFAULT_WAIT_SECONDS: Final = 20
"""How long one receive waits for a message: SQS's longest poll."""

MAX_WAIT_SECONDS: Final = 20
"""The longest a receive may wait, as SQS allows."""

DEFAULT_VISIBILITY_TIMEOUT_SECONDS: Final = 120
"""How long a received message stays hidden from other workers."""

MAX_VISIBILITY_TIMEOUT_SECONDS: Final = 43200
"""The longest visibility timeout SQS allows: twelve hours."""

DEFAULT_EXTEND_EVERY_SECONDS: Final = 30
"""How often a running job's message has its visibility extended."""

JobHandler = Callable[[QueueMessage], Awaitable[JobResult]]
"""Runs the job request one message carries, and returns its result."""


class WorkerSettings(BaseModel):
    """How a worker polls its queue and keeps its messages hidden."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    wait_seconds: int = Field(
        default=DEFAULT_WAIT_SECONDS,
        ge=0,
        le=MAX_WAIT_SECONDS,
    )
    visibility_timeout_seconds: int = Field(
        default=DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
        ge=1,
        le=MAX_VISIBILITY_TIMEOUT_SECONDS,
    )
    extend_every_seconds: float = Field(
        default=DEFAULT_EXTEND_EVERY_SECONDS,
        gt=0,
    )

    @model_validator(mode="after")
    def validate_extension(
        self,
    ) -> "WorkerSettings":
        """Require visibility to be extended before it runs out."""

        if self.extend_every_seconds >= self.visibility_timeout_seconds:
            raise ValueError(
                "A worker must extend a message's visibility more often than its "
                f"visibility timeout of {self.visibility_timeout_seconds} seconds."
            )

        return self


class Settlement(StrEnum):
    """What the worker did with a message once it was done with it."""

    DELETED = "deleted"
    """The job's result is final; the message is gone."""

    LEFT = "left"
    """The message comes back when its visibility timeout runs out."""

    RETURNED = "returned"
    """The worker stopped; the message is visible again at once."""


class SettledMessage(BaseModel):
    """One line of the worker's log: a message, its job, and its settlement.

    A message handed back or left after a failure has no status and no
    invocation, since its job never produced a result.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    message_id: str
    idempotency_key: str | None
    status: JobStatus | None
    invocation_id: UUID | None
    settled: Settlement


def encode_job_result(
    result: JobResult,
) -> str:
    """Return a job result as the one line of JSON that `job run` prints."""

    return json.dumps(
        result.model_dump(
            mode="json",
        ),
        ensure_ascii=False,
    )


def encode_settled_message(
    settled: SettledMessage,
) -> str:
    """Return one settled message as one line of JSON."""

    return json.dumps(
        settled.model_dump(
            mode="json",
        ),
        ensure_ascii=False,
    )


class Worker:
    """Runs the job requests of one queue, one message at a time."""

    def __init__(
        self,
        queue: JobQueue,
        handle: JobHandler,
        *,
        settings: WorkerSettings | None = None,
        results: ResultQueue | None = None,
        log: Callable[[str], None] | None = None,
        report: Callable[[str], None] | None = None,
        heartbeat: Callable[[], None] | None = None,
    ) -> None:
        """Compose a worker.

        Args:
            queue: The queue job requests come from.
            handle: Runs the job request one message carries.
            settings: How to poll and extend; the defaults when omitted.
            results: Where every final result is sent, when given.
            log: Writes one settled message's line; stdout when omitted.
            report: Writes one problem; stderr when omitted.
            heartbeat: Called before every receive and after every
                extension, so a health check can tell the worker is alive.
        """

        self._queue = queue
        self._handle = handle
        self._settings = settings if settings is not None else WorkerSettings()
        self._results = results
        self._log = log if log is not None else _print_line
        self._report = report if report is not None else _print_problem
        self._heartbeat = heartbeat if heartbeat is not None else _nothing

    async def run(
        self,
        stop: asyncio.Event,
    ) -> None:
        """Receive and settle messages until `stop` is set.

        A receive already waiting when `stop` is set finishes first, so the
        worker stops within one wait, and hands back any message it brought.

        Raises:
            Exception: The queue failed, or a handler raised; the message it
                was running stays on the queue.
        """

        while not stop.is_set():
            self._heartbeat()

            message = await asyncio.to_thread(
                self._queue.receive,
                wait_seconds=self._settings.wait_seconds,
                visibility_timeout_seconds=self._settings.visibility_timeout_seconds,
            )

            if message is not None:
                await self.process(message, stop)

    async def process(
        self,
        message: QueueMessage,
        stop: asyncio.Event,
    ) -> SettledMessage:
        """Run one message's job and settle the message; return its settlement.

        Raises:
            Exception: The handler raised; the message stays on the queue.
        """

        key = _readable_key(message.body)

        if stop.is_set():
            return await self._hand_back(message, key)

        job = asyncio.ensure_future(self._handle(message))
        extensions: list[asyncio.Future[None]] = []
        extending = asyncio.create_task(self._extend(message, extensions))
        stopping = asyncio.create_task(stop.wait())

        try:
            await asyncio.wait({job, stopping}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            extending.cancel()
            stopping.cancel()

            if not job.done():
                job.cancel()

            await asyncio.wait({job, extending, stopping})

            #
            # An extension already sent finishes before the message is
            # settled, so it cannot hide a message handed back.
            #
            await asyncio.gather(*extensions, return_exceptions=True)

        if job.cancelled():
            return await self._hand_back(message, key)

        error = job.exception()

        if error is not None:
            self._report(
                f"Message {message.message_id} stays on the queue; running it failed: {error}"
            )
            self._settle(message, key, None, Settlement.LEFT)

            raise error

        return await self._settle_result(message, job.result())

    async def _settle_result(
        self,
        message: QueueMessage,
        result: JobResult,
    ) -> SettledMessage:
        """Leave an incomplete job's message; send and delete a final one."""

        if result.status is JobStatus.INCOMPLETE:
            return self._settle(message, result.idempotency_key, result, Settlement.LEFT)

        if self._results is not None:
            await asyncio.to_thread(
                self._results.send,
                encode_job_result(result),
                idempotency_key=result.idempotency_key,
            )

        await asyncio.to_thread(self._queue.delete, message)

        return self._settle(message, result.idempotency_key, result, Settlement.DELETED)

    async def _hand_back(
        self,
        message: QueueMessage,
        key: str | None,
    ) -> SettledMessage:
        """Make a message visible again at once, for another worker."""

        await asyncio.to_thread(
            self._queue.change_visibility,
            message,
            timeout_seconds=0,
        )

        return self._settle(message, key, None, Settlement.RETURNED)

    async def _extend(
        self,
        message: QueueMessage,
        extensions: list[asyncio.Future[None]],
    ) -> None:
        """Keep a running job's message hidden, until cancelled or refused.

        Each extension is shielded, and recorded, so cancelling the loop
        never abandons one already sent; it beats as it lands, so none goes
        without its heartbeat, however the job ends.
        """

        while True:
            await asyncio.sleep(self._settings.extend_every_seconds)

            extension = asyncio.ensure_future(asyncio.to_thread(self._extend_once, message))
            extensions.append(extension)

            try:
                await asyncio.shield(extension)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._report(
                    f"Could not extend the visibility of message {message.message_id}: {exc}"
                )
                return

    def _extend_once(
        self,
        message: QueueMessage,
    ) -> None:
        """Hide a running job's message again, then beat, in one call from a thread.

        A heartbeat that fails is reported, and the job carries on: the
        health check, finding no fresh beat, is what replaces the worker.

        Raises:
            Exception: The queue refused the extension.
        """

        self._queue.change_visibility(
            message,
            timeout_seconds=self._settings.visibility_timeout_seconds,
        )

        try:
            self._heartbeat()
        except Exception as exc:
            self._report(str(exc))

    def _settle(
        self,
        message: QueueMessage,
        key: str | None,
        result: JobResult | None,
        settled: Settlement,
    ) -> SettledMessage:
        """Log one settled message, and return it."""

        line = SettledMessage(
            message_id=message.message_id,
            idempotency_key=key,
            status=result.status if result is not None else None,
            invocation_id=result.invocation_id if result is not None else None,
            settled=settled,
        )

        self._log(encode_settled_message(line))

        return line


def _readable_key(
    body: bytes,
) -> str | None:
    """Return the idempotency key a message body holds, if it holds a valid one."""

    try:
        data = json.loads(body.decode("utf-8-sig"))
    except ValueError:
        return None

    return readable_idempotency_key(data)


def _print_line(
    line: str,
) -> None:
    """Write one line on stdout at once."""

    print(line, flush=True)


def _print_problem(
    message: str,
) -> None:
    """Write one problem on stderr at once."""

    print(message, file=sys.stderr, flush=True)


def _nothing() -> None:
    """Do nothing; the heartbeat of a worker nothing checks."""


__all__ = [
    "DEFAULT_EXTEND_EVERY_SECONDS",
    "DEFAULT_VISIBILITY_TIMEOUT_SECONDS",
    "DEFAULT_WAIT_SECONDS",
    "MAX_VISIBILITY_TIMEOUT_SECONDS",
    "MAX_WAIT_SECONDS",
    "JobHandler",
    "SettledMessage",
    "Settlement",
    "Worker",
    "WorkerSettings",
    "encode_job_result",
    "encode_settled_message",
]

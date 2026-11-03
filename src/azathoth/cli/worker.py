"""Running the queue worker from the command line (ADR 0107)."""

import asyncio
import signal
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import FrameType
from typing import Any, Final

from pydantic import ValidationError

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.termination import (
    INTERRUPTED_MESSAGE,
    INTERRUPTED_STATUS,
    TERMINATED_MESSAGE,
    TERMINATED_STATUS,
)
from azathoth.cli.tracing import run_traced
from azathoth.inputs import (
    DEFAULT_MAX_INPUT_BYTES,
    S3_SCHEME,
    InputPolicy,
    S3InputLocation,
    S3InputResolver,
    s3_client,
)
from azathoth.jobs import (
    JobResult,
    run_job_content,
    runtime_job_invoker,
    runtime_job_resumer,
)
from azathoth.runtime import AzathothRuntime
from azathoth.telemetry import Telemetry
from azathoth.telemetry.conventions import WORKER_MESSAGE_ID
from azathoth.telemetry.invocations import traced_job, traced_job_invoker
from azathoth.telemetry.runs import tracing_runner
from azathoth.worker import (
    HeartbeatFile,
    JobQueue,
    QueueMessage,
    ResultQueue,
    SqsJobQueue,
    SqsResultQueue,
    Worker,
    WorkerSettings,
    check_heartbeat,
)

WORKER_INPUT_POLICY: Final = InputPolicy()
"""What a worker allowed no S3 location accepts: no references at all.

A message must never read the worker's own disk, so `file://` is never
accepted (ADR 0096, ADR 0107).
"""

MAX_WORKER_INPUT_BYTES: Final = 100 * 1024 * 1024
"""The largest cap a worker may set on one input: 100 MiB.

A resolved input is decoded into its run's context, in the database, so the
ceiling protects the database as much as the worker (ADR 0108).
"""

STOPPING_MESSAGE: Final = "Stopping."
"""What the worker prints on stderr when it is told to stop."""

STOPPED_MESSAGE: Final = "Stopped."
"""What the worker prints on stderr once it has stopped cleanly."""

STOP_SIGNALS: Final = (signal.SIGINT, signal.SIGTERM)
"""The signals that stop the worker: Ctrl-C, and what ECS sends."""


def open_job_queue(
    url: str,
) -> JobQueue:
    """Open the queue job requests come from."""

    return SqsJobQueue(url)


def open_result_queue(
    url: str,
) -> ResultQueue:
    """Open the queue final results are sent to."""

    return SqsResultQueue(url)


def open_s3_client() -> Any:
    """Return the client `s3://` inputs are read with."""

    return s3_client()


def worker_input_policy(
    allowed: Sequence[S3InputLocation],
    *,
    max_bytes: int,
    client: Any | None,
) -> InputPolicy:
    """Return what a worker accepts: `s3://` inside the allowed locations, or nothing.

    A worker allowed no location accepts no scheme at all, so its refusal
    says so.
    """

    if not allowed:
        return InputPolicy(max_bytes=max_bytes)

    return InputPolicy(
        resolvers={S3_SCHEME: S3InputResolver(allowed, client=client)},
        max_bytes=max_bytes,
    )


def input_problems(
    allow_input_buckets: Sequence[str],
    max_input_bytes: int,
) -> tuple[tuple[S3InputLocation, ...], tuple[str, ...]]:
    """Parse the allowed locations and check the cap; return them and any problems."""

    locations: list[S3InputLocation] = []
    problems: list[str] = []

    for value in allow_input_buckets:
        try:
            locations.append(S3InputLocation.parse(value))
        except ValueError as exc:
            problems.append(f"--allow-input-bucket: {exc}")

    if not 1 <= max_input_bytes <= MAX_WORKER_INPUT_BYTES:
        problems.append(
            f"--max-input-bytes: Input should be from 1 to {MAX_WORKER_INPUT_BYTES} bytes."
        )

    return tuple(locations), tuple(problems)


def run_worker(
    queue_url: str,
    *,
    result_queue_url: str | None,
    wait_seconds: int,
    visibility_timeout_seconds: int,
    extend_every_seconds: float,
    heartbeat_file: Path | None,
    allow_input_buckets: Sequence[str] = (),
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
) -> int:
    """Run job requests from a queue, one at a time, until stopped.

    Each settled message is one line of JSON on stdout. The first Ctrl-C or
    SIGTERM prints `Stopping.`, lets a receive in progress finish, stops the
    job running, which releases its run's lease, and hands its message back
    to the queue at once; the worker then prints `Stopped.` and returns 0. A
    second signal stops it where it is, and returns 130 or 143.

    A request's input may be an `s3://` reference inside one of the
    `allow_input_buckets` locations, of at most `max_input_bytes`; with no
    location allowed, it may be no reference at all (ADR 0108).

    Settings that are not valid print why and return 1, before anything is
    opened. A queue that cannot be opened or refuses a call, a heartbeat file
    that cannot be written, and the `worker` extra missing raise
    `WorkerError`, which the CLI prints in one line. S3 that cannot be
    reached raises `InputUnavailableError`, and stops the worker the same
    way, leaving its message on the queue.

    With tracing on, each job is traced as `job run` traces it, with the
    message's ID on its job span (ADR 0100).
    """

    problems: list[str] = []

    try:
        settings = WorkerSettings(
            wait_seconds=wait_seconds,
            visibility_timeout_seconds=visibility_timeout_seconds,
            extend_every_seconds=extend_every_seconds,
        )
    except ValidationError as exc:
        problems.extend(settings_problems(exc))

    locations, input_errors = input_problems(allow_input_buckets, max_input_bytes)
    problems.extend(input_errors)

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)

        return 1

    return run_traced(
        lambda telemetry: _run_traced_worker(
            queue_url,
            result_queue_url=result_queue_url,
            settings=settings,
            heartbeat_file=heartbeat_file,
            locations=locations,
            max_input_bytes=max_input_bytes,
            telemetry=telemetry,
        )
    )


def check_worker_health(
    heartbeat_file: Path,
    *,
    max_age_seconds: float,
) -> int:
    """Return 0 when a worker beat within `max_age_seconds`, and 1 when it did not.

    A healthy worker's heartbeat age is printed on stdout; an unhealthy
    one's reason on stderr.
    """

    health = check_heartbeat(heartbeat_file, max_age_seconds=max_age_seconds)

    print(health.message, file=sys.stdout if health.healthy else sys.stderr)

    return 0 if health.healthy else 1


def settings_problems(
    error: ValidationError,
) -> tuple[str, ...]:
    """Return one line per problem with the worker's settings, naming its option."""

    problems: list[str] = []

    for problem in error.errors():
        message = str(problem["msg"]).removeprefix("Value error, ")

        if problem["loc"]:
            option = "--" + str(problem["loc"][0]).replace("_", "-")
            problems.append(f"{option}: {message}.")
        else:
            problems.append(message)

    return tuple(problems)


def _run_traced_worker(
    queue_url: str,
    *,
    result_queue_url: str | None,
    settings: WorkerSettings,
    heartbeat_file: Path | None,
    locations: tuple[S3InputLocation, ...],
    max_input_bytes: int,
    telemetry: Telemetry,
) -> int:
    """Open the queues, S3 and the database, then serve until stopped."""

    queue = open_job_queue(queue_url)
    results = open_result_queue(result_queue_url) if result_queue_url is not None else None

    #
    # A worker allowed S3 locations makes its client now, so a missing
    # extra stops it before it receives anything.
    #
    policy = worker_input_policy(
        locations,
        max_bytes=max_input_bytes,
        client=open_s3_client() if locations else None,
    )

    configuration = CliRuntimeConfiguration.from_environment()
    stores = repositories(configuration)

    heartbeat = HeartbeatFile(heartbeat_file) if heartbeat_file is not None else None

    if heartbeat is not None:
        heartbeat.beat()

    runtimes: list[AzathothRuntime] = []

    def load() -> AzathothRuntime:
        """Compose the runtime on the first job that needs it, then reuse it."""

        if not runtimes:
            runtimes.append(load_runtime(configuration))

        return runtimes[0]

    runner = tracing_runner(
        telemetry,
        journal=stores.run_journal,
        leases=stores.run_leases,
        children=stores.run_children,
    )
    invoke = traced_job_invoker(
        telemetry,
        runtime_job_invoker(
            load,
            invocation_repository=stores.invocations,
            run_repository=stores.runs,
            invocation_run_repository=stores.invocation_runs,
            runner=runner,
        ),
    )
    resume = runtime_job_resumer(
        load,
        invocation_repository=stores.invocations,
        run_repository=stores.runs,
        invocation_run_repository=stores.invocation_runs,
        revision_repository=stores.production_revisions,
        journal=stores.run_journal,
        runner=runner,
    )

    async def handle(
        message: QueueMessage,
    ) -> JobResult:
        """Run one message's job request inside its job span."""

        with traced_job(telemetry) as trace:
            trace.span.set_attributes({WORKER_MESSAGE_ID: message.message_id})

            result = await run_job_content(
                message.body,
                policy=policy,
                store=stores.content,
                invocation_repository=stores.invocations,
                invoke=invoke,
                resume=resume,
            )

            trace.record(result)

        return result

    worker = Worker(
        queue,
        handle,
        settings=settings,
        results=results,
        heartbeat=heartbeat.beat if heartbeat is not None else None,
    )

    return asyncio.run(_serve(worker))


async def _serve(
    worker: Worker,
) -> int:
    """Run the worker until a signal stops it; return the command's status."""

    stop = asyncio.Event()
    task = asyncio.current_task()
    forced: list[int] = []

    def on_signal(
        signum: int,
    ) -> None:
        """Drain on the first signal; stop where it is on the second."""

        if not stop.is_set():
            print(STOPPING_MESSAGE, file=sys.stderr, flush=True)
            stop.set()
            return

        if not forced and task is not None:
            forced.append(signum)
            task.cancel()

    restore = _stop_on_signals(asyncio.get_running_loop(), on_signal)

    try:
        await worker.run(stop)
    except asyncio.CancelledError:
        if not forced:
            raise

        if task is not None:
            task.uncancel()

        if forced[0] == signal.SIGINT:
            print(INTERRUPTED_MESSAGE, file=sys.stderr, flush=True)

            return INTERRUPTED_STATUS

        print(TERMINATED_MESSAGE, file=sys.stderr, flush=True)

        return TERMINATED_STATUS
    finally:
        restore()

    print(STOPPED_MESSAGE, file=sys.stderr, flush=True)

    return 0


def _stop_on_signals(
    loop: asyncio.AbstractEventLoop,
    on_signal: Callable[[int], None],
) -> Callable[[], None]:
    """Route SIGINT and SIGTERM to `on_signal` in the loop; return what undoes it.

    Where the loop cannot take signals, as on Windows, Python's own handlers
    pass them to the loop instead. Either way, the handlers in place before
    are restored afterwards.
    """

    previous = {signum: signal.getsignal(signum) for signum in STOP_SIGNALS}
    in_loop: list[int] = []

    def forward(
        signum: int,
        frame: FrameType | None,
    ) -> None:
        loop.call_soon_threadsafe(on_signal, signum)

    for signum in STOP_SIGNALS:
        try:
            loop.add_signal_handler(signum, on_signal, signum)
            in_loop.append(signum)
        except (NotImplementedError, RuntimeError):
            signal.signal(signum, forward)

    def restore() -> None:
        for signum in in_loop:
            loop.remove_signal_handler(signum)

        for signum, handler in previous.items():
            signal.signal(signum, handler)

    return restore


__all__ = [
    "MAX_WORKER_INPUT_BYTES",
    "STOPPED_MESSAGE",
    "STOPPING_MESSAGE",
    "STOP_SIGNALS",
    "WORKER_INPUT_POLICY",
    "check_worker_health",
    "input_problems",
    "open_s3_client",
    "open_job_queue",
    "open_result_queue",
    "run_worker",
    "settings_problems",
    "worker_input_policy",
]

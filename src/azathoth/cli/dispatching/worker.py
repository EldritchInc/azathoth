"""Queue worker command dispatch for the Azathoth CLI (ADR 0107)."""

from argparse import Namespace
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast

from azathoth.cli.parsing import (
    WORKER_ACTION_ATTRIBUTE,
    WORKER_ALLOW_INPUT_BUCKET_ATTRIBUTE,
    WORKER_EXTEND_EVERY_ATTRIBUTE,
    WORKER_HEALTH_ACTION,
    WORKER_HEARTBEAT_FILE_ATTRIBUTE,
    WORKER_MAX_AGE_ATTRIBUTE,
    WORKER_MAX_INPUT_BYTES_ATTRIBUTE,
    WORKER_QUEUE_URL_ATTRIBUTE,
    WORKER_RESULT_QUEUE_URL_ATTRIBUTE,
    WORKER_RUN_ACTION,
    WORKER_VISIBILITY_TIMEOUT_ATTRIBUTE,
    WORKER_WAIT_SECONDS_ATTRIBUTE,
)


class WorkerRunner(Protocol):
    """Runs the worker over one queue until it is stopped."""

    def __call__(
        self,
        queue_url: str,
        *,
        result_queue_url: str | None,
        wait_seconds: int,
        visibility_timeout_seconds: int,
        extend_every_seconds: float,
        heartbeat_file: Path | None,
        allow_input_buckets: Sequence[str],
        max_input_bytes: int,
    ) -> int: ...


class WorkerHealthChecker(Protocol):
    """Checks one worker's heartbeat file."""

    def __call__(
        self,
        heartbeat_file: Path,
        *,
        max_age_seconds: float,
    ) -> int: ...


def dispatch_worker_command(
    arguments: Namespace,
    *,
    run_worker: WorkerRunner,
    check_worker_health: WorkerHealthChecker,
) -> int | None:
    """Dispatch one parsed queue worker command."""

    action = cast(
        str | None,
        getattr(
            arguments,
            WORKER_ACTION_ATTRIBUTE,
            None,
        ),
    )

    if action == WORKER_RUN_ACTION:
        return run_worker(
            cast(str, getattr(arguments, WORKER_QUEUE_URL_ATTRIBUTE)),
            result_queue_url=cast(
                str | None,
                getattr(arguments, WORKER_RESULT_QUEUE_URL_ATTRIBUTE),
            ),
            wait_seconds=cast(int, getattr(arguments, WORKER_WAIT_SECONDS_ATTRIBUTE)),
            visibility_timeout_seconds=cast(
                int,
                getattr(arguments, WORKER_VISIBILITY_TIMEOUT_ATTRIBUTE),
            ),
            extend_every_seconds=cast(
                float,
                getattr(arguments, WORKER_EXTEND_EVERY_ATTRIBUTE),
            ),
            heartbeat_file=cast(
                Path | None,
                getattr(arguments, WORKER_HEARTBEAT_FILE_ATTRIBUTE),
            ),
            allow_input_buckets=tuple(
                cast(list[str], getattr(arguments, WORKER_ALLOW_INPUT_BUCKET_ATTRIBUTE))
            ),
            max_input_bytes=cast(int, getattr(arguments, WORKER_MAX_INPUT_BYTES_ATTRIBUTE)),
        )

    if action == WORKER_HEALTH_ACTION:
        return check_worker_health(
            cast(Path, getattr(arguments, WORKER_HEARTBEAT_FILE_ATTRIBUTE)),
            max_age_seconds=cast(float, getattr(arguments, WORKER_MAX_AGE_ATTRIBUTE)),
        )

    return None


__all__ = [
    "WorkerHealthChecker",
    "WorkerRunner",
    "dispatch_worker_command",
]

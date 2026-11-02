"""Why a worker cannot start, or cannot carry on (ADR 0107)."""

from typing import Final

MISSING_WORKER_EXTRA_MESSAGE: Final = (
    "azathoth worker needs boto3, which is not installed; install azathoth-ai[worker]."
)
"""What a worker without the `worker` extra reports."""


class WorkerError(Exception):
    """The worker cannot start, or cannot carry on; its message says why."""


class WorkerUnavailableError(WorkerError):
    """boto3 is not installed."""

    def __init__(
        self,
    ) -> None:
        super().__init__(MISSING_WORKER_EXTRA_MESSAGE)


class QueueError(WorkerError):
    """A queue cannot be used, or refused a call."""


class HeartbeatError(WorkerError):
    """The heartbeat file cannot be written."""


__all__ = [
    "MISSING_WORKER_EXTRA_MESSAGE",
    "HeartbeatError",
    "QueueError",
    "WorkerError",
    "WorkerUnavailableError",
]

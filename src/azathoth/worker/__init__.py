"""The queue worker: runs job requests from a queue, one at a time (ADR 0107)."""

from azathoth.worker.errors import (
    MISSING_WORKER_EXTRA_MESSAGE,
    HeartbeatError,
    QueueError,
    WorkerError,
    WorkerUnavailableError,
)
from azathoth.worker.heartbeat import (
    DEFAULT_MAX_HEARTBEAT_AGE_SECONDS,
    HeartbeatFile,
    WorkerHealth,
    check_heartbeat,
)
from azathoth.worker.loop import (
    DEFAULT_EXTEND_EVERY_SECONDS,
    DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
    DEFAULT_WAIT_SECONDS,
    MAX_VISIBILITY_TIMEOUT_SECONDS,
    MAX_WAIT_SECONDS,
    JobHandler,
    SettledMessage,
    Settlement,
    Worker,
    WorkerSettings,
    encode_job_result,
    encode_settled_message,
)
from azathoth.worker.queue import (
    JobQueue,
    QueueMessage,
    ResultQueue,
)
from azathoth.worker.sqs import (
    SqsJobQueue,
    SqsResultQueue,
    queue_region,
    sqs_client,
)

__all__ = [
    "DEFAULT_EXTEND_EVERY_SECONDS",
    "DEFAULT_MAX_HEARTBEAT_AGE_SECONDS",
    "DEFAULT_VISIBILITY_TIMEOUT_SECONDS",
    "DEFAULT_WAIT_SECONDS",
    "MAX_VISIBILITY_TIMEOUT_SECONDS",
    "MAX_WAIT_SECONDS",
    "MISSING_WORKER_EXTRA_MESSAGE",
    "HeartbeatError",
    "HeartbeatFile",
    "JobHandler",
    "JobQueue",
    "QueueError",
    "QueueMessage",
    "ResultQueue",
    "SettledMessage",
    "Settlement",
    "SqsJobQueue",
    "SqsResultQueue",
    "Worker",
    "WorkerError",
    "WorkerHealth",
    "WorkerSettings",
    "WorkerUnavailableError",
    "check_heartbeat",
    "encode_job_result",
    "encode_settled_message",
    "queue_region",
    "sqs_client",
]

"""The queues a worker takes job requests from and sends results to (ADR 0107)."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class QueueMessage(BaseModel):
    """One message received from a job queue.

    The body is exactly a job request (ADR 0097). The receipt handle names
    this receipt of the message, which is what deleting it or changing its
    visibility needs.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    message_id: str = Field(min_length=1)
    receipt_handle: str = Field(min_length=1)
    body: bytes


class JobQueue(Protocol):
    """A queue of job requests, delivered at least once.

    A received message is hidden from other receivers for its visibility
    timeout, and is delivered again once that runs out unless it was deleted.
    Every method blocks, so the worker calls them from a thread.
    """

    def receive(
        self,
        *,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> QueueMessage | None:
        """Return the next message, waiting up to `wait_seconds` for one."""

        ...

    def delete(
        self,
        message: QueueMessage,
    ) -> None:
        """Remove one received message for good."""

        ...

    def change_visibility(
        self,
        message: QueueMessage,
        *,
        timeout_seconds: int,
    ) -> None:
        """Hide one received message for `timeout_seconds` from now; 0 shows it at once."""

        ...


class ResultQueue(Protocol):
    """A queue the worker sends every final job result to."""

    def send(
        self,
        body: str,
        *,
        idempotency_key: str | None,
    ) -> None:
        """Send one job result, as one line of JSON, with its request's key."""

        ...


__all__ = [
    "JobQueue",
    "QueueMessage",
    "ResultQueue",
]

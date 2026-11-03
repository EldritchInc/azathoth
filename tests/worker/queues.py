"""An in-memory job queue that records every call the worker makes (ADR 0107)."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from azathoth.jobs import JobResult
from azathoth.worker import QueueMessage


@dataclass
class QueuedMessage:
    """One message on the queue, and when it is next visible."""

    message: QueueMessage
    visible_at: float = 0.0
    receives: int = 0
    deleted: bool = False


@dataclass
class MemoryQueue:
    """A queue in memory, with visibility timeouts, recording each call in order.

    `calls` holds `("receive",)`, `("delete", <MESSAGE_ID>)` and
    `("visibility", <MESSAGE_ID>, <SECONDS>)`. An empty receive waits
    briefly, so a worker polling an empty queue does not spin.

    With `extension_gate`, an extension, any visibility change but to 0,
    sets `extension_arrived` and waits for the gate to open before it lands,
    so a test can hold one in flight for exactly as long as it needs.
    """

    messages: list[QueuedMessage] = field(default_factory=list)
    calls: list[tuple[object, ...]] = field(default_factory=list)
    received: list[tuple[int, int]] = field(default_factory=list)
    on_receive: Callable[[QueueMessage], None] | None = None
    fail_visibility: bool = False
    extension_gate: threading.Event | None = None
    extension_arrived: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def put(
        self,
        message_id: str,
        body: bytes,
    ) -> None:
        """Add one message, visible at once."""

        with self.lock:
            self.messages.append(
                QueuedMessage(
                    message=QueueMessage(
                        message_id=message_id,
                        receipt_handle=f"receipt-{message_id}",
                        body=body,
                    )
                )
            )

    def receive(
        self,
        *,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> QueueMessage | None:
        """Return the first visible message, hidden for the visibility timeout."""

        with self.lock:
            self.calls.append(("receive",))
            self.received.append((wait_seconds, visibility_timeout_seconds))
            now = time.monotonic()

            for queued in self.messages:
                if not queued.deleted and queued.visible_at <= now:
                    queued.visible_at = now + visibility_timeout_seconds
                    queued.receives += 1
                    message = queued.message
                    break
            else:
                message = None

        if message is None:
            time.sleep(0.01)
            return None

        if self.on_receive is not None:
            self.on_receive(message)

        return message

    def delete(
        self,
        message: QueueMessage,
    ) -> None:
        """Remove one message for good."""

        with self.lock:
            self.calls.append(("delete", message.message_id))
            self.find(message.message_id).deleted = True

    def change_visibility(
        self,
        message: QueueMessage,
        *,
        timeout_seconds: int,
    ) -> None:
        """Hide one message for the given number of seconds from now."""

        if timeout_seconds and self.extension_gate is not None:
            self.extension_arrived.set()

            assert self.extension_gate.wait(10), "the extension was never let through"

        with self.lock:
            self.calls.append(("visibility", message.message_id, timeout_seconds))

            if self.fail_visibility:
                raise RuntimeError("The receipt handle has expired.")

            self.find(message.message_id).visible_at = time.monotonic() + timeout_seconds

    def find(
        self,
        message_id: str,
    ) -> QueuedMessage:
        """Return one queued message by its ID."""

        (queued,) = (queued for queued in self.messages if queued.message.message_id == message_id)

        return queued

    def visibility_changes(
        self,
        message_id: str,
    ) -> list[int]:
        """Return every visibility timeout set on one message, in order."""

        return [
            int(str(call[2]))
            for call in self.calls
            if call[0] == "visibility" and call[1] == message_id
        ]


@dataclass
class MemoryResults:
    """A result queue in memory, recording what it was sent and the queue's calls."""

    queue: MemoryQueue
    sent: list[tuple[str, str | None]] = field(default_factory=list)

    def send(
        self,
        body: str,
        *,
        idempotency_key: str | None,
    ) -> None:
        """Record one result, and its place among the job queue's calls."""

        with self.queue.lock:
            self.queue.calls.append(("result", idempotency_key))
            self.sent.append((body, idempotency_key))


def results_of(
    results: MemoryResults,
) -> list[JobResult]:
    """Decode every result a result queue was sent."""

    return [JobResult.model_validate_json(body) for body, _ in results.sent]

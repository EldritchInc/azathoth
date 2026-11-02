"""A job queue in a directory, that several worker processes can share (ADR 0107).

It stands in for SQS across processes, as only the tests need, with SQS's
semantics: delivery at least once, a visibility timeout per receipt, and a
receipt that stops working once the message is received again.

Every change is one atomic rename or one change of a file's time:

- `bodies/<ID>` holds a message's body, and never changes;
- `visible/<ID>` is a message any receiver may take;
- `hidden/<ID>.<RECEIPT>` is a received message, hidden until the file's
  modification time; a receiver takes one whose time has passed by renaming
  it to a new receipt, so only one receiver ever wins it;
- `deleted/<ID>` is a message gone for good;
- `receives.log` records every receive, one `<ID> <PID>` line each;
- `results/` holds every result sent, one file each.
"""

import json
import os
import time
import uuid
from pathlib import Path

from azathoth.worker import QueueError, QueueMessage

POLL_SECONDS = 0.05
"""How often an empty receive looks again, while it waits."""


class DirectoryQueue:
    """A `JobQueue` over one directory."""

    def __init__(
        self,
        root: Path,
    ) -> None:
        self.root = root

        for name in ("bodies", "visible", "hidden", "deleted", "results"):
            (root / name).mkdir(parents=True, exist_ok=True)

    def put(
        self,
        message_id: str,
        body: bytes,
    ) -> None:
        """Add one message, visible at once."""

        assert "." not in message_id

        (self.root / "bodies" / message_id).write_bytes(body)
        (self.root / "visible" / message_id).touch()

    def receive(
        self,
        *,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> QueueMessage | None:
        """Take the first visible message, waiting up to `wait_seconds` for one."""

        deadline = time.monotonic() + wait_seconds

        while True:
            taken = self._take(visibility_timeout_seconds)

            if taken is not None:
                return taken

            if time.monotonic() >= deadline:
                return None

            time.sleep(POLL_SECONDS)

    def delete(
        self,
        message: QueueMessage,
    ) -> None:
        """Remove one received message for good, by its current receipt."""

        try:
            os.rename(self._hidden(message), self.root / "deleted" / message.message_id)
        except FileNotFoundError:
            raise QueueError(
                f"The receipt of message {message.message_id} is no longer valid."
            ) from None

    def change_visibility(
        self,
        message: QueueMessage,
        *,
        timeout_seconds: int,
    ) -> None:
        """Hide one received message for `timeout_seconds` from now, by its current receipt."""

        until = time.time() + timeout_seconds

        try:
            os.utime(self._hidden(message), (until, until))
        except FileNotFoundError:
            raise QueueError(
                f"The receipt of message {message.message_id} is no longer valid."
            ) from None

    def send(
        self,
        body: str,
        *,
        idempotency_key: str | None,
    ) -> None:
        """Record one result, with its key."""

        path = self.root / "results" / f"{time.time_ns()}-{uuid.uuid4().hex}.json"
        path.write_text(json.dumps({"body": body, "key": idempotency_key}), encoding="utf-8")

    def deleted(
        self,
    ) -> list[str]:
        """Return the ID of every message deleted, sorted."""

        return sorted(path.name for path in (self.root / "deleted").iterdir())

    def receives(
        self,
    ) -> list[tuple[str, int]]:
        """Return every receive, in order, as `(message ID, receiver PID)`."""

        log = self.root / "receives.log"

        if not log.exists():
            return []

        return [
            (message_id, int(pid))
            for message_id, pid in (
                line.split() for line in log.read_text(encoding="utf-8").splitlines()
            )
        ]

    def results(
        self,
    ) -> list[tuple[str, str | None]]:
        """Return every result sent, in the order sent, as `(body, key)`."""

        return [
            (record["body"], record["key"])
            for record in (
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((self.root / "results").iterdir())
            )
        ]

    def is_visible(
        self,
        message_id: str,
    ) -> bool:
        """Return whether a message, not deleted, may be received now."""

        if (self.root / "visible" / message_id).exists():
            return True

        return any(
            path.stat().st_mtime <= time.time()
            for path in (self.root / "hidden").glob(f"{message_id}.*")
        )

    def _take(
        self,
        visibility_timeout_seconds: int,
    ) -> QueueMessage | None:
        """Win one visible or lapsed message by renaming it, or return `None`."""

        now = time.time()
        candidates = [path for path in sorted((self.root / "visible").iterdir())]
        candidates += [
            path for path in sorted((self.root / "hidden").iterdir()) if path.stat().st_mtime <= now
        ]

        for path in candidates:
            message_id = path.name.split(".", 1)[0]
            receipt = uuid.uuid4().hex
            hidden = self.root / "hidden" / f"{message_id}.{receipt}"

            try:
                os.rename(path, hidden)
            except FileNotFoundError:
                continue

            until = time.time() + visibility_timeout_seconds
            os.utime(hidden, (until, until))

            with (self.root / "receives.log").open("a", encoding="utf-8") as log:
                log.write(f"{message_id} {os.getpid()}\n")

            return QueueMessage(
                message_id=message_id,
                receipt_handle=receipt,
                body=(self.root / "bodies" / message_id).read_bytes(),
            )

        return None

    def _hidden(
        self,
        message: QueueMessage,
    ) -> Path:
        """Return where a message is hidden under one receipt."""

        return self.root / "hidden" / f"{message.message_id}.{message.receipt_handle}"

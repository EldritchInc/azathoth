"""The lock that keeps one remote server on an SQLite file (ADR 0135).

SQLite serves one remote process on one machine: several processes on one
file queue every writer behind every other, and processes on several
machines, or a file on a network share, can corrupt it. So `azathoth
remote serve` holds an exclusive lock on a file beside an SQLite database
for as long as it serves, and a second server on the same file is refused
before it serves anything. The operating system releases the lock when the
process ends, however it ends, so no lock is ever left behind.

Commands other than `remote serve`, and the editor, never take the lock,
so they go on working beside a running server. A PostgreSQL database takes
no lock: several servers are what it is for.

The lock file is left in place when the server stops; only the lock on it
means anything.
"""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Final

from azathoth.persistence import DatabaseLocation, SQLiteLocation

SERVE_LOCK_SUFFIX: Final = ".serve-lock"
"""What the lock file's name adds to the database file's name."""

SQLITE_SERVES_ONE_MESSAGE: Final = (
    "SQLite serves one remote process on one machine. For more than one process, or a "
    "database another machine reaches, use PostgreSQL."
)
"""Why a second server on one SQLite file is refused, and what to use instead."""


class RemoteAlreadyServedError(RuntimeError):
    """Another `azathoth remote serve` holds the lock on this SQLite database."""

    def __init__(
        self,
        database: Path,
    ) -> None:
        super().__init__(
            f"Another azathoth remote serve is already serving {database}. "
            f"{SQLITE_SERVES_ONE_MESSAGE}"
        )


def serve_lock_path(
    database: Path,
) -> Path:
    """Return the lock file beside an SQLite database file."""

    return database.with_name(f"{database.name}{SERVE_LOCK_SUFFIX}")


@contextmanager
def serving_lock(
    location: DatabaseLocation,
) -> Iterator[None]:
    """Hold the serving lock on an SQLite database while the block runs.

    A PostgreSQL database takes no lock.

    Raises:
        RemoteAlreadyServedError: Another process holds the lock.
    """

    if not isinstance(location, SQLiteLocation):
        yield
        return

    path = serve_lock_path(location.path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a+b") as handle:
        try:
            _lock(handle)
        except OSError as exc:
            raise RemoteAlreadyServedError(location.path) from exc

        try:
            yield
        finally:
            _unlock(handle)


if sys.platform == "win32":
    import msvcrt

    def _lock(
        handle: IO[bytes],
    ) -> None:
        """Lock the file's first byte, failing at once when another process holds it."""

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(
        handle: IO[bytes],
    ) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(
        handle: IO[bytes],
    ) -> None:
        """Lock the whole file, failing at once when another open file holds it."""

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(
        handle: IO[bytes],
    ) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = [
    "SERVE_LOCK_SUFFIX",
    "SQLITE_SERVES_ONE_MESSAGE",
    "RemoteAlreadyServedError",
    "serve_lock_path",
    "serving_lock",
]

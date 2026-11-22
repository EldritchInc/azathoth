"""SQLite, the database Azathoth keeps by default (ADR 0102)."""

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Final

from azathoth.persistence.database import (
    READ_ONLY_LOCK_MESSAGE,
    InitializationOutcome,
    Parameter,
    Row,
    Table,
    run_backfills,
)
from azathoth.persistence.dialect import Dialect, identifier, render
from azathoth.persistence.errors import (
    IntegrityError,
    NestedTransactionError,
    ReadOnlyTransactionError,
)
from azathoth.persistence.location import SQLiteLocation

BUSY_TIMEOUT_SECONDS: Final = 30.0
"""How long a transaction waits for another process's to commit before it gives up."""

JOURNAL_MODE: Final = "wal"
"""The journal mode a file is put in, so readers carry on while a writer commits."""

READ_ONLY_ERROR_NAME: Final = "SQLITE_READONLY"
"""The SQLite error a write under `PRAGMA query_only` raises."""


def bound(
    parameters: Sequence[Parameter],
) -> tuple[Parameter, ...]:
    """Return statement parameters as either database binds them.

    A boolean is bound as the integer 0 or 1, which is what an `INTEGER`
    column holds in both.
    """

    return tuple(int(value) if isinstance(value, bool) else value for value in parameters)


class SQLiteSession:
    """The statements of one SQLite transaction."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        read_only: bool = False,
    ) -> None:
        self._connection = connection
        self._read_only = read_only

    def execute(
        self,
        statement: str,
        parameters: Sequence[Parameter] = (),
    ) -> int:
        return self._cursor(statement, parameters).rowcount

    def fetchone(
        self,
        statement: str,
        parameters: Sequence[Parameter] = (),
    ) -> Row | None:
        row = self._cursor(statement, parameters).fetchone()

        return None if row is None else tuple(row)

    def fetchall(
        self,
        statement: str,
        parameters: Sequence[Parameter] = (),
    ) -> list[Row]:
        return [tuple(row) for row in self._cursor(statement, parameters).fetchall()]

    def _cursor(
        self,
        statement: str,
        parameters: Sequence[Parameter],
    ) -> sqlite3.Cursor:
        try:
            return self._connection.execute(
                render(statement, Dialect.SQLITE),
                bound(parameters),
            )
        except sqlite3.IntegrityError as exc:
            raise IntegrityError(str(exc)) from exc
        except sqlite3.OperationalError as exc:
            if self._read_only and exc.sqlite_errorname == READ_ONLY_ERROR_NAME:
                raise ReadOnlyTransactionError(str(exc)) from exc

            raise


class SQLiteDatabase:
    """An SQLite file, opened afresh for each transaction.

    The file is put in WAL mode the first time it is opened, which it then
    keeps: readers see what was committed when they began reading, and
    carry on while a writer writes and commits.

    Every transaction that may write begins immediately, taking the file's
    write lock, and waits up to `BUSY_TIMEOUT_SECONDS` for another
    process's transaction to commit. A transaction that began deferred and
    then wrote could be refused at once, without waiting, whenever another
    process was writing, so processes that share a file, such as the
    children of one map (ADR 0106), would fail each other. Taking the lock
    first serializes them instead.

    A read-only transaction begins deferred, under `PRAGMA query_only`, and
    takes no write lock, so it never waits for a writer and a writer never
    waits for it.

    A transaction begun inside another on the same thread is refused: it
    would open a second connection, which waits for the first's write lock.
    """

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self._location = SQLiteLocation(path=Path(path))
        self._journal_set = False
        self._journal_lock = threading.Lock()
        self._inside = threading.local()

    @property
    def dialect(
        self,
    ) -> Dialect:
        return Dialect.SQLITE

    @property
    def location(
        self,
    ) -> SQLiteLocation:
        return self._location

    @property
    def path(
        self,
    ) -> Path:
        """Return the database file's path."""

        return self._location.path

    def transaction(
        self,
        *,
        lock: str | None = None,
        read_only: bool = False,
    ) -> AbstractContextManager[SQLiteSession]:
        """Run a block as one transaction.

        Every transaction that may write takes `BEGIN IMMEDIATE`, which in
        SQLite locks the whole file for writing, so a lock names a table
        only to check it. A read-only transaction takes `BEGIN`, deferred.

        Raises:
            NestedTransactionError: A transaction of this database is
                already in progress on this thread.
            ValueError: Both `lock` and `read_only` were given.
        """

        if lock is not None:
            if read_only:
                raise ValueError(READ_ONLY_LOCK_MESSAGE)

            identifier(lock)

        return self._transaction(read_only=read_only)

    @contextmanager
    def _transaction(
        self,
        *,
        read_only: bool,
    ) -> Iterator[SQLiteSession]:
        if getattr(self._inside, "active", False):
            raise NestedTransactionError()

        self._inside.active = True

        try:
            with self._connected(read_only=read_only) as session:
                yield session
        finally:
            self._inside.active = False

    @contextmanager
    def _connected(
        self,
        *,
        read_only: bool,
    ) -> Iterator[SQLiteSession]:
        connection = sqlite3.connect(
            self._location.path,
            isolation_level=None,
            timeout=BUSY_TIMEOUT_SECONDS,
        )

        try:
            self._set_journal(connection)

            if read_only:
                connection.execute("PRAGMA query_only = ON")
                connection.execute("BEGIN")
            else:
                connection.execute("BEGIN IMMEDIATE")

            try:
                yield SQLiteSession(connection, read_only=read_only)
            except BaseException:
                connection.execute("ROLLBACK")
                raise

            connection.execute("COMMIT")
        finally:
            connection.close()

    def _set_journal(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """Put the file in WAL mode, once for this database.

        The mode is kept in the file, so this changes nothing after the
        first time. When another process holds the file and it cannot be
        changed now, or its filesystem cannot keep a WAL, the transaction
        goes ahead in the mode the file has, and the next one tries again.
        """

        if self._journal_set:
            return

        #
        # Two threads may both find the mode unset; setting it twice changes
        # nothing, and the lock keeps them from changing it at once.
        #
        with self._journal_lock:
            try:
                row = connection.execute(f"PRAGMA journal_mode = {JOURNAL_MODE}").fetchone()
            except sqlite3.OperationalError:
                return

            self._journal_set = row is not None and str(row[0]).lower() == JOURNAL_MODE

    def prepare(
        self,
        tables: Sequence[Table],
    ) -> None:
        """Create the tables that are missing, as SQLite repositories always have."""

        self.initialize(tables)

    def initialize(
        self,
        tables: Sequence[Table],
    ) -> InitializationOutcome:
        """Create every table that is missing, then run every backfill."""

        with self.transaction() as session:
            existing = {
                row[0]
                for row in session.fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
            }

            missing = [table for table in tables if table.name not in existing]

            for table in tables:
                for statement in table.statements:
                    session.execute(statement)

            run_backfills(session, tables)

        return InitializationOutcome.CREATED if missing else InitializationOutcome.CURRENT

    def close(
        self,
    ) -> None:
        """Do nothing: an SQLite database holds no connection between transactions."""


__all__ = [
    "BUSY_TIMEOUT_SECONDS",
    "JOURNAL_MODE",
    "SQLiteDatabase",
    "SQLiteSession",
    "bound",
]

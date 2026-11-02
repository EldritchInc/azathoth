"""SQLite, the database Azathoth keeps by default (ADR 0102)."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Final

from azathoth.persistence.database import (
    InitializationOutcome,
    Parameter,
    Row,
    Table,
)
from azathoth.persistence.dialect import Dialect, identifier, render
from azathoth.persistence.errors import IntegrityError
from azathoth.persistence.location import SQLiteLocation

BUSY_TIMEOUT_SECONDS: Final = 30.0
"""How long a transaction waits for another process's to commit before it gives up."""


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
    ) -> None:
        self._connection = connection

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


class SQLiteDatabase:
    """An SQLite file, opened afresh for each transaction.

    Every transaction begins immediately, taking the file's write lock, and
    waits up to `BUSY_TIMEOUT_SECONDS` for another process's transaction to
    commit. A transaction that began deferred and then wrote could be
    refused at once, without waiting, whenever another process was writing,
    so processes that share a file, such as the children of one map
    (ADR 0106), would fail each other. Taking the lock first serializes them
    instead.
    """

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self._location = SQLiteLocation(path=Path(path))

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
    ) -> AbstractContextManager[SQLiteSession]:
        """Run a block as one transaction.

        Every transaction takes `BEGIN IMMEDIATE`, which in SQLite locks the
        whole file for writing, so a lock names a table only to check it.
        """

        if lock is not None:
            identifier(lock)

        return self._transaction()

    @contextmanager
    def _transaction(
        self,
    ) -> Iterator[SQLiteSession]:
        connection = sqlite3.connect(
            self._location.path,
            isolation_level=None,
            timeout=BUSY_TIMEOUT_SECONDS,
        )

        try:
            connection.execute("BEGIN IMMEDIATE")

            try:
                yield SQLiteSession(connection)
            except BaseException:
                connection.execute("ROLLBACK")
                raise

            connection.execute("COMMIT")
        finally:
            connection.close()

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
        """Create every table that is missing."""

        with self.transaction() as session:
            existing = {
                row[0]
                for row in session.fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
            }

            missing = [table for table in tables if table.name not in existing]

            for table in tables:
                for statement in table.statements:
                    session.execute(statement)

        return InitializationOutcome.CREATED if missing else InitializationOutcome.CURRENT

    def close(
        self,
    ) -> None:
        """Do nothing: an SQLite database holds no connection between transactions."""


__all__ = [
    "SQLiteDatabase",
    "SQLiteSession",
    "bound",
]

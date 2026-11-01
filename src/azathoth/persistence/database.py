"""The database every repository is written against (ADR 0102)."""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from azathoth.persistence.dialect import Dialect
from azathoth.persistence.location import DatabaseLocation

SCHEMA_TABLE: Final = "azathoth_schema"
"""The table in which a PostgreSQL database records its schema version."""

SCHEMA_VERSION: Final = 1
"""The schema version this Azathoth uses."""

Parameter = str | int | float | bytes | None
"""A value bound to a statement's `?`."""

Row = tuple[object, ...]
"""One row a query returned."""


@dataclass(frozen=True)
class Table:
    """One table a repository keeps, as the statements that create it.

    The statements use `IF NOT EXISTS` and the dialect tokens, such as
    `{sequence}`, so they create the same table in either database, and
    creating it again changes nothing.
    """

    name: str
    statements: tuple[str, ...]


class InitializationOutcome(StrEnum):
    """What initializing a database did."""

    CREATED = "created"
    CURRENT = "current"


class Session(Protocol):
    """The statements of one transaction."""

    def execute(
        self,
        statement: str,
        parameters: Sequence[Parameter] = (),
    ) -> int:
        """Execute one statement, and return how many rows it changed.

        Raises:
            IntegrityError: The statement would break a constraint.
        """

        ...

    def fetchone(
        self,
        statement: str,
        parameters: Sequence[Parameter] = (),
    ) -> Row | None:
        """Execute one query and return its first row, or None."""

        ...

    def fetchall(
        self,
        statement: str,
        parameters: Sequence[Parameter] = (),
    ) -> list[Row]:
        """Execute one query and return every row."""

        ...


class Database(Protocol):
    """A database in which repositories keep their tables.

    Each repository call is one transaction. A transaction commits when its
    block ends, and rolls back when the block raises.
    """

    @property
    def dialect(
        self,
    ) -> Dialect:
        """Return the SQL dialect the database speaks."""

        ...

    @property
    def location(
        self,
    ) -> DatabaseLocation:
        """Return where the database is."""

        ...

    def transaction(
        self,
        *,
        lock: str | None = None,
    ) -> AbstractContextManager[Session]:
        """Run a block as one transaction.

        With `lock`, the transaction first takes an exclusive write lock on
        that table, so writers serialize while readers carry on: numbering
        a new revision reads the latest and writes the next.

        Raises:
            IntegrityError: A statement in the block broke a constraint.
        """

        ...

    def prepare(
        self,
        tables: Sequence[Table],
    ) -> None:
        """Make sure a repository's tables are ready to use.

        SQLite creates them. PostgreSQL never runs DDL here: it checks that
        the database was initialized with this Azathoth's schema.

        Raises:
            DatabaseSchemaError: The PostgreSQL schema is missing or is not
                this Azathoth's version.
        """

        ...

    def initialize(
        self,
        tables: Sequence[Table],
    ) -> InitializationOutcome:
        """Create every table that is missing, and record the schema version.

        It is safe to run again, and, in PostgreSQL, from several processes
        at once.

        Raises:
            DatabaseSchemaTooNewError: The PostgreSQL schema is newer than
                this Azathoth's.
        """

        ...

    def close(
        self,
    ) -> None:
        """Release the database's connection, if it holds one."""

        ...


__all__ = [
    "SCHEMA_TABLE",
    "SCHEMA_VERSION",
    "Database",
    "InitializationOutcome",
    "Parameter",
    "Row",
    "Session",
    "Table",
]

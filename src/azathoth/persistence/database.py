"""The database every repository is written against (ADR 0102)."""

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from azathoth.persistence.dialect import Dialect
from azathoth.persistence.location import DatabaseLocation

SCHEMA_TABLE: Final = "azathoth_schema"
"""The table in which a PostgreSQL database records its schema version."""

SCHEMA_VERSION: Final = 7
"""The schema version this Azathoth uses.

Version 2 adds the tables that record a run while it executes (ADR 0105).
Version 3 adds the tables that record revision lineage and portfolio
provenance (ADR 0122). Version 4 adds the table that records who declared
each portfolio entry's data policy (ADR 0123). Version 5 adds the table of
the bearer tokens a remote issues (ADR 0124). Version 6 adds the table of
the last portfolio read from each remote (ADR 0125). Version 7 adds the
table of the remotes an instance names (ADR 0126).
"""

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

    A table added after others may need rows for what those tables already
    hold, such as the lineage of revisions imported before it existed. Its
    `backfill` writes them. Initializing runs every backfill once all of its
    tables are created, in the same transaction, given the names of those
    tables, so a backfill reads only tables that exist. A backfill writes
    only rows that are missing, so running it again changes nothing.
    """

    name: str
    statements: tuple[str, ...]
    backfill: "Callable[[Session, frozenset[str]], None] | None" = None


class InitializationOutcome(StrEnum):
    """What initializing a database did."""

    CREATED = "created"
    UPGRADED = "upgraded"
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
        """Create every table that is missing, run every backfill, and record the schema version.

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


def run_backfills(
    session: Session,
    tables: Sequence[Table],
) -> None:
    """Run every table's backfill, in order, given the names of all the tables."""

    present = frozenset(table.name for table in tables)

    for table in tables:
        if table.backfill is not None:
            table.backfill(session, present)


__all__ = [
    "SCHEMA_TABLE",
    "SCHEMA_VERSION",
    "Database",
    "InitializationOutcome",
    "Parameter",
    "Row",
    "Session",
    "Table",
    "run_backfills",
]

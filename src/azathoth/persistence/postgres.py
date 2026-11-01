"""PostgreSQL, the database Azathoth shares between processes (ADR 0102).

psycopg is imported only when a PostgreSQL database is opened, and only with
the `postgres` extra installed.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol

from azathoth.persistence.database import (
    SCHEMA_TABLE,
    SCHEMA_VERSION,
    InitializationOutcome,
    Parameter,
    Row,
    Table,
)
from azathoth.persistence.dialect import Dialect, identifier, render
from azathoth.persistence.errors import (
    DatabaseNotInitializedError,
    DatabaseSchemaOutdatedError,
    DatabaseSchemaTooNewError,
    DatabaseUnavailableError,
    IntegrityError,
)
from azathoth.persistence.location import PostgresLocation
from azathoth.persistence.sqlite import bound

INITIALIZATION_LOCK: Final = 0x417A6174686F7468 & 0x7FFFFFFFFFFFFFFF
"""The advisory lock that serializes initialization: "Azathoth", as a bigint."""

SCHEMA_STATEMENTS: Final = (
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE} (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        version INTEGER NOT NULL,
        initialized_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)
"""The statements that create the table recording the schema version."""


class PostgresCursor(Protocol):
    """The part of a psycopg cursor Azathoth uses."""

    def fetchone(
        self,
    ) -> tuple[object, ...] | None: ...

    def fetchall(
        self,
    ) -> list[tuple[object, ...]]: ...


class PostgresConnection(Protocol):
    """The part of a psycopg connection Azathoth uses, in autocommit mode."""

    @property
    def closed(
        self,
    ) -> bool: ...

    @property
    def broken(
        self,
    ) -> bool: ...

    def execute(
        self,
        query: str,
        params: Sequence[Parameter],
    ) -> PostgresCursor: ...

    def close(
        self,
    ) -> None: ...


@dataclass(frozen=True)
class PostgresDriver:
    """How to connect, and which of the driver's errors mean what."""

    connect: Callable[[str], PostgresConnection]
    integrity_error: type[Exception]
    operational_error: type[Exception]


def psycopg_driver() -> PostgresDriver:
    """Return psycopg 3 as the driver.

    Raises:
        DatabaseUnavailableError: psycopg is not installed.
    """

    try:
        import psycopg
    except ImportError as exc:
        raise DatabaseUnavailableError() from exc

    def connect(
        url: str,
    ) -> PostgresConnection:
        connection: PostgresConnection = psycopg.connect(url, autocommit=True)

        return connection

    return PostgresDriver(
        connect=connect,
        integrity_error=psycopg.IntegrityError,
        operational_error=psycopg.OperationalError,
    )


class PostgresSession:
    """The statements of one PostgreSQL transaction."""

    def __init__(
        self,
        connection: PostgresConnection,
        driver: PostgresDriver,
    ) -> None:
        self._connection = connection
        self._driver = driver

    def execute(
        self,
        statement: str,
        parameters: Sequence[Parameter] = (),
    ) -> None:
        self._cursor(statement, parameters)

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
    ) -> PostgresCursor:
        #
        # Parameters are always passed, even when there are none, so that
        # psycopg turns every escaped %% back into %.
        #
        try:
            return self._connection.execute(
                render(statement, Dialect.POSTGRES),
                bound(parameters),
            )
        except self._driver.integrity_error as exc:
            raise IntegrityError(str(exc)) from exc


class PostgresDatabase:
    """A PostgreSQL database, over one connection kept for the life of the process.

    The connection is opened when the database is first used. A connection
    found closed or broken, such as one the server dropped while it sat
    idle, is opened again before the next transaction begins.
    """

    def __init__(
        self,
        location: PostgresLocation | str,
        *,
        driver: PostgresDriver | None = None,
    ) -> None:
        self._location = (
            location if isinstance(location, PostgresLocation) else PostgresLocation(location)
        )
        self._driver = driver if driver is not None else psycopg_driver()
        self._connection: PostgresConnection | None = None
        self._checked = False

    @property
    def dialect(
        self,
    ) -> Dialect:
        return Dialect.POSTGRES

    @property
    def location(
        self,
    ) -> PostgresLocation:
        return self._location

    def transaction(
        self,
        *,
        lock: str | None = None,
    ) -> AbstractContextManager[PostgresSession]:
        """Run a block as one transaction.

        A lock takes `LOCK TABLE … IN EXCLUSIVE MODE` on the table, which
        serializes writers to it and never blocks its readers.
        """

        return self._transaction(None if lock is None else identifier(lock))

    @contextmanager
    def _transaction(
        self,
        lock: str | None,
    ) -> Iterator[PostgresSession]:
        connection = self._begin()

        try:
            session = PostgresSession(connection, self._driver)

            if lock is not None:
                session.execute(f"LOCK TABLE {lock} IN EXCLUSIVE MODE")

            yield session
        except BaseException:
            if not connection.closed and not connection.broken:
                with suppress(Exception):
                    connection.execute("ROLLBACK", ())

            raise

        connection.execute("COMMIT", ())

    def _begin(
        self,
    ) -> PostgresConnection:
        """Begin a transaction, opening the connection again once if it was dropped."""

        connection = self._open()

        try:
            connection.execute("BEGIN", ())
        except self._driver.operational_error:
            self._discard()
            connection = self._open()
            connection.execute("BEGIN", ())

        return connection

    def _open(
        self,
    ) -> PostgresConnection:
        """Return the connection, opening it when there is none, or it is unusable."""

        if self._connection is not None and (self._connection.closed or self._connection.broken):
            self._discard()

        if self._connection is None:
            self._connection = self._driver.connect(self._location.url)

        return self._connection

    def _discard(
        self,
    ) -> None:
        """Close and forget the connection."""

        if self._connection is not None:
            with suppress(Exception):
                self._connection.close()

        self._connection = None

    def prepare(
        self,
        tables: Sequence[Table],
    ) -> None:
        """Check, once per process, that the database holds this Azathoth's schema.

        It never runs DDL: `initialize` creates the schema.

        Raises:
            DatabaseNotInitializedError: The database holds no schema yet.
            DatabaseSchemaOutdatedError: Its schema is older than this Azathoth's.
            DatabaseSchemaTooNewError: Its schema is newer than this Azathoth's.
        """

        if self._checked:
            return

        with self.transaction() as session:
            version = _recorded_version(session)

        if version is None:
            raise DatabaseNotInitializedError(self._location)

        if version < SCHEMA_VERSION:
            raise DatabaseSchemaOutdatedError(
                self._location,
                found=version,
                expected=SCHEMA_VERSION,
            )

        if version > SCHEMA_VERSION:
            raise DatabaseSchemaTooNewError(
                self._location,
                found=version,
                expected=SCHEMA_VERSION,
            )

        self._checked = True

    def initialize(
        self,
        tables: Sequence[Table],
    ) -> InitializationOutcome:
        """Create the schema, under an advisory lock, and record its version.

        Several processes may initialize at once: each waits for the lock,
        and the later ones find the schema already there.

        Raises:
            DatabaseSchemaTooNewError: The schema is newer than this Azathoth's.
        """

        now = datetime.now(UTC).isoformat()

        with self.transaction() as session:
            session.fetchone("SELECT pg_advisory_xact_lock(?)", (INITIALIZATION_LOCK,))

            version = _recorded_version(session)

            if version is not None and version > SCHEMA_VERSION:
                raise DatabaseSchemaTooNewError(
                    self._location,
                    found=version,
                    expected=SCHEMA_VERSION,
                )

            missing = [table for table in tables if not _exists(session, table.name)]

            for statement in SCHEMA_STATEMENTS:
                session.execute(statement)

            for table in tables:
                for statement in table.statements:
                    session.execute(statement)

            session.execute(
                f"""
                INSERT INTO {SCHEMA_TABLE} (id, version, initialized_at, updated_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    version = excluded.version,
                    updated_at = excluded.updated_at
                """,
                (SCHEMA_VERSION, now, now),
            )

        self._checked = True

        if version is None or missing:
            return InitializationOutcome.CREATED

        return InitializationOutcome.CURRENT

    def close(
        self,
    ) -> None:
        """Close the connection, if one is open."""

        self._discard()


def _exists(
    session: PostgresSession,
    table: str,
) -> bool:
    """Return whether a table exists on the session's search path."""

    row = session.fetchone("SELECT to_regclass(?) IS NOT NULL", (identifier(table),))

    return row is not None and row[0] is True


def _recorded_version(
    session: PostgresSession,
) -> int | None:
    """Return the schema version the database records, or None when it records none."""

    if not _exists(session, SCHEMA_TABLE):
        return None

    row = session.fetchone(f"SELECT version FROM {SCHEMA_TABLE} WHERE id = 1")

    if row is None:
        return None

    version = row[0]

    if not isinstance(version, int):
        raise TypeError(f"The recorded schema version {version!r} is not an integer.")

    return version


__all__ = [
    "INITIALIZATION_LOCK",
    "SCHEMA_STATEMENTS",
    "PostgresConnection",
    "PostgresCursor",
    "PostgresDatabase",
    "PostgresDriver",
    "PostgresSession",
    "psycopg_driver",
]

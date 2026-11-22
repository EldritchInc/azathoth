"""PostgreSQL, the database Azathoth shares between processes (ADR 0102).

psycopg is imported only when a PostgreSQL database is opened, and only with
the `postgres` extra installed.
"""

import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol

from azathoth.persistence.database import (
    READ_ONLY_LOCK_MESSAGE,
    SCHEMA_TABLE,
    SCHEMA_VERSION,
    InitializationOutcome,
    Parameter,
    Row,
    Table,
    run_backfills,
)
from azathoth.persistence.dialect import Dialect, identifier, render
from azathoth.persistence.errors import (
    DatabaseBusyError,
    DatabaseNotInitializedError,
    DatabaseSchemaOutdatedError,
    DatabaseSchemaTooNewError,
    DatabaseUnavailableError,
    IntegrityError,
    NestedTransactionError,
    ReadOnlyTransactionError,
)
from azathoth.persistence.location import PostgresLocation
from azathoth.persistence.sqlite import bound

DEFAULT_POOL_SIZE: Final = 8
"""How many connections a PostgreSQL database holds open at most, unless told otherwise."""

POOL_WAIT_SECONDS: Final = 30.0
"""How long a transaction waits for a pooled connection before it gives up."""

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

    @property
    def rowcount(
        self,
    ) -> int: ...

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
    read_only_error: type[Exception]


def psycopg_driver() -> PostgresDriver:
    """Return psycopg 3 as the driver.

    Raises:
        DatabaseUnavailableError: psycopg is not installed.
    """

    try:
        import psycopg
        import psycopg.errors
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
        read_only_error=psycopg.errors.ReadOnlySqlTransaction,
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
        except self._driver.read_only_error as exc:
            raise ReadOnlyTransactionError(str(exc)) from exc


class PostgresDatabase:
    """A PostgreSQL database, over a pool of connections shared by the process's threads.

    Each transaction borrows a connection of its own and gives it back when
    it commits or rolls back, so transactions on different threads run
    together. At most `pool_size` connections are open at once; a
    transaction that finds every one in use waits up to `wait_seconds` for
    one to be given back, then raises `DatabaseBusyError`.

    Connections are opened as they are first needed, and idle ones are
    kept for the next transaction. A connection found closed or broken,
    such as one the server dropped while it sat idle, is replaced before a
    transaction begins on it.
    """

    def __init__(
        self,
        location: PostgresLocation | str,
        *,
        driver: PostgresDriver | None = None,
        pool_size: int = DEFAULT_POOL_SIZE,
        wait_seconds: float = POOL_WAIT_SECONDS,
    ) -> None:
        """Pool connections to one database.

        Raises:
            ValueError: `pool_size` is below 1, or `wait_seconds` is negative.
        """

        if pool_size < 1:
            raise ValueError(f"A pool holds at least one connection, not {pool_size}.")

        if wait_seconds < 0:
            raise ValueError(f"A transaction cannot wait {wait_seconds:g} seconds.")

        self._location = (
            location if isinstance(location, PostgresLocation) else PostgresLocation(location)
        )
        self._driver = driver if driver is not None else psycopg_driver()
        self._pool_size = pool_size
        self._wait_seconds = wait_seconds
        self._idle: list[PostgresConnection] = []
        self._open = 0
        self._generation = 0
        self._available = threading.Condition(threading.Lock())
        self._inside = threading.local()
        self._checked = False
        self._checking = threading.Lock()

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

    @property
    def pool_size(
        self,
    ) -> int:
        """Return how many connections the pool may hold open at once."""

        return self._pool_size

    def transaction(
        self,
        *,
        lock: str | None = None,
        read_only: bool = False,
    ) -> AbstractContextManager[PostgresSession]:
        """Run a block as one transaction, on a connection borrowed from the pool.

        A lock takes `LOCK TABLE … IN EXCLUSIVE MODE` on the table, which
        serializes writers to it and never blocks its readers. A read-only
        transaction begins `READ ONLY`, and the server refuses its writes.

        Raises:
            DatabaseBusyError: No connection was free within `wait_seconds`.
            NestedTransactionError: A transaction of this database is
                already in progress on this thread.
            ValueError: Both `lock` and `read_only` were given.
        """

        if lock is not None and read_only:
            raise ValueError(READ_ONLY_LOCK_MESSAGE)

        return self._transaction(
            None if lock is None else identifier(lock),
            begin="BEGIN READ ONLY" if read_only else "BEGIN",
        )

    @contextmanager
    def _transaction(
        self,
        lock: str | None,
        *,
        begin: str,
    ) -> Iterator[PostgresSession]:
        if getattr(self._inside, "active", False):
            raise NestedTransactionError()

        self._inside.active = True

        try:
            borrowed, generation = self._borrow()

            try:
                connection = self._begin(borrowed, begin)
            except BaseException:
                self._give_back(None, generation, keep=False)
                raise

            keep = False

            try:
                session = PostgresSession(connection, self._driver)

                try:
                    if lock is not None:
                        session.execute(f"LOCK TABLE {lock} IN EXCLUSIVE MODE")

                    yield session
                except BaseException:
                    #
                    # A connection rolled back cleanly is kept; one that is
                    # broken, or that could not roll back, is closed.
                    #
                    if _usable(connection):
                        with suppress(Exception):
                            connection.execute("ROLLBACK", ())
                            keep = _usable(connection)

                    raise

                connection.execute("COMMIT", ())
                keep = True
            finally:
                self._give_back(connection, generation, keep=keep)
        finally:
            self._inside.active = False

    def _borrow(
        self,
    ) -> tuple[PostgresConnection | None, int]:
        """Take an idle connection, or room to open one, waiting while every one is in use.

        Returns None in place of a connection when there is room to open
        one, so that it is opened outside the pool's lock.

        Raises:
            DatabaseBusyError: None was free within `wait_seconds`.
        """

        deadline = time.monotonic() + self._wait_seconds

        with self._available:
            while not self._idle and self._open >= self._pool_size:
                remaining = deadline - time.monotonic()

                if remaining <= 0 or not self._available.wait(remaining):
                    if self._idle or self._open < self._pool_size:
                        break

                    raise DatabaseBusyError(
                        self._location,
                        pool_size=self._pool_size,
                        waited_seconds=self._wait_seconds,
                    )

            if self._idle:
                return self._idle.pop(), self._generation

            self._open += 1

            return None, self._generation

    def _begin(
        self,
        connection: PostgresConnection | None,
        begin: str,
    ) -> PostgresConnection:
        """Begin a transaction, opening a connection if there is none or it is unusable.

        A connection the server dropped is replaced once. When beginning
        fails, whatever connection it holds is closed, so its place in the
        pool can be given back.
        """

        try:
            if connection is not None and not _usable(connection):
                _close(connection)
                connection = None

            if connection is None:
                connection = self._driver.connect(self._location.url)

            try:
                connection.execute(begin, ())
            except self._driver.operational_error:
                _close(connection)
                connection = None
                connection = self._driver.connect(self._location.url)
                connection.execute(begin, ())

            return connection
        except BaseException:
            if connection is not None:
                _close(connection)

            raise

    def _give_back(
        self,
        connection: PostgresConnection | None,
        generation: int,
        *,
        keep: bool,
    ) -> None:
        """Return a connection to the pool, or close it and free its place.

        A connection is kept for the next transaction only when its own
        committed, it is usable, and the pool was not closed while it was
        borrowed. None frees the place of a connection never opened.
        """

        with self._available:
            if (
                keep
                and connection is not None
                and _usable(connection)
                and generation == self._generation
            ):
                self._idle.append(connection)
            else:
                if connection is not None:
                    _close(connection)

                self._open -= 1

            self._available.notify()

    def prepare(
        self,
        tables: Sequence[Table],
    ) -> None:
        """Check, once per process, that the database holds this Azathoth's schema.

        It never runs DDL: `initialize` creates the schema. Threads that
        prepare at once check it once between them.

        Raises:
            DatabaseNotInitializedError: The database holds no schema yet.
            DatabaseSchemaOutdatedError: Its schema is older than this Azathoth's.
            DatabaseSchemaTooNewError: Its schema is newer than this Azathoth's.
        """

        with self._checking:
            if self._checked:
                return

            with self.transaction(read_only=True) as session:
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
        and the later ones find the schema already there. A schema of an
        earlier version gains the tables it lacks, every backfill fills the
        rows they need for what the database already holds, and it is then
        recorded as this version.

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

            run_backfills(session, tables)

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

        if version is None:
            return InitializationOutcome.CREATED

        if version < SCHEMA_VERSION:
            return InitializationOutcome.UPGRADED

        if missing:
            return InitializationOutcome.CREATED

        return InitializationOutcome.CURRENT

    def close(
        self,
    ) -> None:
        """Close every idle connection now, and each one in use when it is given back.

        The database may be used again afterwards: the next transaction
        opens a connection afresh.
        """

        with self._available:
            idle, self._idle = self._idle, []
            self._open -= len(idle)
            self._generation += 1
            self._available.notify_all()

        for connection in idle:
            _close(connection)


def _usable(
    connection: PostgresConnection,
) -> bool:
    """Return whether a connection is neither closed nor broken."""

    return not connection.closed and not connection.broken


def _close(
    connection: PostgresConnection,
) -> None:
    """Close a connection, ignoring any error closing it raises."""

    with suppress(Exception):
        connection.close()


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
    "DEFAULT_POOL_SIZE",
    "INITIALIZATION_LOCK",
    "POOL_WAIT_SECONDS",
    "SCHEMA_STATEMENTS",
    "PostgresConnection",
    "PostgresCursor",
    "PostgresDatabase",
    "PostgresDriver",
    "PostgresSession",
    "psycopg_driver",
]

"""Tests of PostgreSQL itself: its schema, its connection and its driver (ADR 0102).

Those that need a server run only with `AZATHOTH_TEST_POSTGRES_URL`.
"""

import sys
import threading
from collections.abc import Sequence

import pytest

from azathoth.persistence import (
    MISSING_DRIVER_MESSAGE,
    SCHEMA_TABLE,
    SCHEMA_VERSION,
    DatabaseNotInitializedError,
    DatabaseSchemaOutdatedError,
    DatabaseSchemaTooNewError,
    DatabaseUnavailableError,
    InitializationOutcome,
    IntegrityError,
    Parameter,
    PostgresDatabase,
    PostgresLocation,
    open_database,
)
from azathoth.persistence.postgres import (
    INITIALIZATION_LOCK,
    PostgresConnection,
    PostgresCursor,
    PostgresDriver,
)
from tests.persistence.test_database import TABLES, insert, ready, thing_ids

URL = "postgresql://azathoth:hunter2@db.example.internal:5432/azathoth"

SHOWN = "postgresql://azathoth@db.example.internal:5432/azathoth"


# The driver


def test_without_psycopg_a_postgresql_database_cannot_be_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "psycopg", None)

    with pytest.raises(DatabaseUnavailableError) as raised:
        open_database(URL)

    assert str(raised.value) == MISSING_DRIVER_MESSAGE
    assert MISSING_DRIVER_MESSAGE == (
        "AZATHOTH_DATABASE names a PostgreSQL database, but psycopg is not installed; "
        "install azathoth-ai[postgres]."
    )


def test_opening_names_nothing_secret_in_its_errors() -> None:
    assert str(DatabaseNotInitializedError(PostgresLocation(URL))) == (
        f"Database {SHOWN} is not initialized; run azathoth init."
    )
    assert str(DatabaseSchemaOutdatedError(PostgresLocation(URL), found=1, expected=2)) == (
        f"Database {SHOWN} has schema version 1, but this Azathoth uses version 2; "
        "run azathoth init."
    )
    assert str(DatabaseSchemaTooNewError(PostgresLocation(URL), found=3, expected=1)) == (
        f"Database {SHOWN} has schema version 3, newer than the version 1 this Azathoth "
        "uses; upgrade Azathoth."
    )


# The connection, over a scripted driver


class DroppedError(Exception):
    """The scripted driver's operational error."""


class DuplicateError(Exception):
    """The scripted driver's integrity error."""


class ScriptedCursor:
    def __init__(
        self,
        rows: list[tuple[object, ...]],
    ) -> None:
        self._rows = rows

    @property
    def rowcount(
        self,
    ) -> int:
        return len(self._rows)

    def fetchone(
        self,
    ) -> tuple[object, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(
        self,
    ) -> list[tuple[object, ...]]:
        return list(self._rows)


class ScriptedConnection:
    """A connection that records what it executes, and fails when told to."""

    def __init__(
        self,
        log: list[str],
        *,
        fail_begin: bool = False,
        fail_on: str | None = None,
    ) -> None:
        self.log = log
        self.closed = False
        self.broken = False
        self._fail_begin = fail_begin
        self._fail_on = fail_on

    def execute(
        self,
        query: str,
        params: Sequence[Parameter],
    ) -> PostgresCursor:
        self.log.append(query.strip())

        if query == "BEGIN" and self._fail_begin:
            self._fail_begin = False
            self.broken = True
            raise DroppedError("server closed the connection unexpectedly")

        if self._fail_on is not None and self._fail_on in query:
            raise DuplicateError("duplicate key value violates unique constraint")

        return ScriptedCursor([])

    def close(
        self,
    ) -> None:
        self.log.append("<close>")
        self.closed = True


class ScriptedDriver:
    """A driver handing out scripted connections, recording each one."""

    def __init__(
        self,
        *connections: ScriptedConnection,
    ) -> None:
        self.log: list[str] = []
        self._connections = list(connections)
        self.opened: list[ScriptedConnection] = []

    def connect(
        self,
        url: str,
    ) -> PostgresConnection:
        connection = self._connections.pop(0) if self._connections else ScriptedConnection(self.log)
        connection.log = self.log
        self.log.append("<connect>")
        self.opened.append(connection)

        return connection

    def driver(
        self,
    ) -> PostgresDriver:
        return PostgresDriver(
            connect=self.connect,
            integrity_error=DuplicateError,
            operational_error=DroppedError,
        )


def scripted(
    *connections: ScriptedConnection,
) -> tuple[PostgresDatabase, ScriptedDriver]:
    """Return a database over a scripted driver, and the driver."""

    script = ScriptedDriver(*connections)

    return PostgresDatabase(URL, driver=script.driver()), script


def test_one_connection_serves_every_transaction() -> None:
    database, script = scripted()

    for _ in range(3):
        with database.transaction() as session:
            session.execute("SELECT 1")

    assert script.log.count("<connect>") == 1
    assert script.log.count("BEGIN") == 3
    assert script.log.count("COMMIT") == 3


def test_a_transaction_renders_postgresql_parameters() -> None:
    database, script = scripted()

    with database.transaction() as session:
        session.execute("SELECT payload FROM t WHERE id = ? AND name LIKE '50%'", ("x",))

    assert "SELECT payload FROM t WHERE id = %s AND name LIKE '50%%'" in script.log


def test_a_lock_takes_the_table_exclusively_after_beginning() -> None:
    database, script = scripted()

    with database.transaction(lock="workflow_specification_revisions"):
        pass

    assert script.log[1:] == [
        "BEGIN",
        "LOCK TABLE workflow_specification_revisions IN EXCLUSIVE MODE",
        "COMMIT",
    ]


def test_a_block_that_raises_rolls_back() -> None:
    database, script = scripted()

    with pytest.raises(RuntimeError), database.transaction():
        raise RuntimeError("abandon")

    assert script.log[1:] == ["BEGIN", "ROLLBACK"]


def test_a_driver_integrity_error_becomes_azathoths() -> None:
    database, script = scripted(ScriptedConnection([], fail_on="INSERT"))

    with pytest.raises(IntegrityError, match="duplicate key"), database.transaction() as session:
        session.execute("INSERT INTO t VALUES (?)", ("x",))

    assert script.log[-1] == "ROLLBACK"


def test_a_dropped_connection_is_opened_again_before_the_next_transaction() -> None:
    database, script = scripted(ScriptedConnection([], fail_begin=True))

    with database.transaction() as session:
        session.execute("SELECT 1")

    assert script.log == [
        "<connect>",
        "BEGIN",
        "<close>",
        "<connect>",
        "BEGIN",
        "SELECT 1",
        "COMMIT",
    ]


def test_a_connection_found_broken_is_replaced() -> None:
    database, script = scripted()

    with database.transaction():
        pass

    script.opened[0].broken = True

    with database.transaction():
        pass

    assert script.log.count("<connect>") == 2


def test_a_broken_connection_is_not_rolled_back() -> None:
    database, script = scripted()

    with pytest.raises(RuntimeError), database.transaction():
        script.opened[0].broken = True
        raise RuntimeError("lost")

    assert "ROLLBACK" not in script.log


def test_closing_closes_the_connection() -> None:
    database, script = scripted()

    with database.transaction():
        pass

    database.close()

    assert script.log[-1] == "<close>"


def test_the_initialization_lock_is_a_positive_bigint() -> None:
    assert 0 < INITIALIZATION_LOCK < 2**63


# A real server


def record_version(
    database: PostgresDatabase,
    version: int,
) -> None:
    """Overwrite the schema version a database records."""

    with database.transaction() as session:
        session.execute(f"UPDATE {SCHEMA_TABLE} SET version = ? WHERE id = 1", (version,))


def test_an_uninitialized_database_is_refused(
    postgres_database: PostgresDatabase,
) -> None:
    with pytest.raises(DatabaseNotInitializedError, match="run azathoth init"):
        postgres_database.prepare(TABLES)


def test_preparing_never_creates_a_table(
    postgres_database: PostgresDatabase,
) -> None:
    with pytest.raises(DatabaseNotInitializedError):
        postgres_database.prepare(TABLES)

    with postgres_database.transaction() as session:
        assert session.fetchone("SELECT to_regclass('things')") == (None,)


def test_initializing_records_the_schema_version(
    postgres_database: PostgresDatabase,
) -> None:
    assert postgres_database.initialize(TABLES) is InitializationOutcome.CREATED

    with postgres_database.transaction() as session:
        assert session.fetchone(f"SELECT id, version FROM {SCHEMA_TABLE}") == (1, SCHEMA_VERSION)


def test_another_process_sees_the_initialized_schema(
    postgres_url: str,
) -> None:
    first = PostgresDatabase(postgres_url)
    second = PostgresDatabase(postgres_url)

    try:
        ready(first)
        insert(first, "thing-1")

        second.prepare(TABLES)

        assert thing_ids(second) == ["thing-1"]
    finally:
        first.close()
        second.close()


def test_an_older_schema_is_refused_until_initialized_again(
    postgres_url: str,
) -> None:
    writer = PostgresDatabase(postgres_url)
    reader = PostgresDatabase(postgres_url)

    try:
        writer.initialize(TABLES)
        record_version(writer, SCHEMA_VERSION - 1)

        with pytest.raises(DatabaseSchemaOutdatedError):
            reader.prepare(TABLES)

        writer.initialize(TABLES)
        reader.prepare(TABLES)
    finally:
        writer.close()
        reader.close()


def test_a_newer_schema_is_refused_and_never_initialized_over(
    postgres_url: str,
) -> None:
    writer = PostgresDatabase(postgres_url)
    reader = PostgresDatabase(postgres_url)

    try:
        writer.initialize(TABLES)
        record_version(writer, SCHEMA_VERSION + 1)

        with pytest.raises(DatabaseSchemaTooNewError, match="upgrade Azathoth"):
            reader.prepare(TABLES)

        with pytest.raises(DatabaseSchemaTooNewError):
            reader.initialize(TABLES)
    finally:
        writer.close()
        reader.close()


def test_several_processes_may_initialize_at_once(
    postgres_url: str,
) -> None:
    databases = [PostgresDatabase(postgres_url) for _ in range(4)]
    outcomes: list[InitializationOutcome] = []
    failures: list[BaseException] = []

    def initialize(
        database: PostgresDatabase,
    ) -> None:
        try:
            outcomes.append(database.initialize(TABLES))
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=initialize, args=(database,)) for database in databases]

    try:
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
    finally:
        for database in databases:
            database.close()

    assert failures == []
    assert sorted(outcomes) == sorted(
        [InitializationOutcome.CREATED] + [InitializationOutcome.CURRENT] * 3
    )


def test_concurrent_writers_never_take_the_same_revision_number(
    postgres_url: str,
) -> None:
    from tests.persistence.test_database import next_revision

    databases = [PostgresDatabase(postgres_url) for _ in range(4)]
    numbers: list[int] = []
    failures: list[BaseException] = []

    ready(databases[0])

    def write(
        database: PostgresDatabase,
    ) -> None:
        try:
            for _ in range(5):
                numbers.append(next_revision(database, "thing-1"))
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=write, args=(database,)) for database in databases]

    try:
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
    finally:
        for database in databases:
            database.close()

    assert failures == []
    assert sorted(numbers) == list(range(1, 21))


def test_a_connection_the_server_dropped_is_opened_again(
    postgres_url: str,
) -> None:
    database = PostgresDatabase(postgres_url)
    admin = PostgresDatabase(postgres_url)

    try:
        ready(database)

        with database.transaction() as session:
            row = session.fetchone("SELECT pg_backend_pid()")

        assert row is not None
        assert isinstance(row[0], int)

        with admin.transaction() as session:
            session.fetchone("SELECT pg_terminate_backend(?)", (row[0],))

        insert(database, "thing-1")

        assert thing_ids(database) == ["thing-1"]
    finally:
        database.close()
        admin.close()

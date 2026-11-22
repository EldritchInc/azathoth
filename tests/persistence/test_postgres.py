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
    DatabaseBusyError,
    DatabaseNotInitializedError,
    DatabaseSchemaOutdatedError,
    DatabaseSchemaTooNewError,
    DatabaseUnavailableError,
    InitializationOutcome,
    IntegrityError,
    NestedTransactionError,
    Parameter,
    PostgresDatabase,
    PostgresLocation,
    ReadOnlyTransactionError,
    open_database,
)
from azathoth.persistence.database import READ_ONLY_LOCK_MESSAGE
from azathoth.persistence.postgres import (
    DEFAULT_POOL_SIZE,
    INITIALIZATION_LOCK,
    POOL_WAIT_SECONDS,
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


class RefusedWriteError(Exception):
    """The scripted driver's error for a write in a read-only transaction."""


WRITES = ("INSERT", "UPDATE", "DELETE")


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
        self._read_only = False

    def execute(
        self,
        query: str,
        params: Sequence[Parameter],
    ) -> PostgresCursor:
        self.log.append(query.strip())

        if query.startswith("BEGIN") and self._fail_begin:
            self._fail_begin = False
            self.broken = True
            raise DroppedError("server closed the connection unexpectedly")

        if query.startswith("BEGIN"):
            self._read_only = query == "BEGIN READ ONLY"

        if self._read_only and query.strip().startswith(WRITES):
            raise RefusedWriteError("cannot execute INSERT in a read-only transaction")

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
        refuse_connects: int = 0,
    ) -> None:
        self.log: list[str] = []
        self._connections = list(connections)
        self.opened: list[ScriptedConnection] = []
        self._refuse_connects = refuse_connects

    def connect(
        self,
        url: str,
    ) -> PostgresConnection:
        if self._refuse_connects:
            self._refuse_connects -= 1
            self.log.append("<refused>")
            raise DroppedError("connection refused")

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
            read_only_error=RefusedWriteError,
        )


def scripted(
    *connections: ScriptedConnection,
    pool_size: int = DEFAULT_POOL_SIZE,
    wait_seconds: float = POOL_WAIT_SECONDS,
    refuse_connects: int = 0,
) -> tuple[PostgresDatabase, ScriptedDriver]:
    """Return a database over a scripted driver, and the driver."""

    script = ScriptedDriver(*connections, refuse_connects=refuse_connects)
    database = PostgresDatabase(
        URL,
        driver=script.driver(),
        pool_size=pool_size,
        wait_seconds=wait_seconds,
    )

    return database, script


WAIT = 10.0
"""How long a test waits for another thread before it counts as stuck."""


class Holder:
    """A thread that holds a transaction open until it is let go."""

    def __init__(
        self,
        database: PostgresDatabase,
    ) -> None:
        self.inside = threading.Event()
        self.release = threading.Event()
        self.failures: list[BaseException] = []
        self._database = database
        self._thread = threading.Thread(target=self._hold)
        self._thread.start()

    def _hold(
        self,
    ) -> None:
        try:
            with self._database.transaction() as session:
                session.execute("SELECT 1")
                self.inside.set()
                self.release.wait(WAIT)
        except BaseException as error:
            self.failures.append(error)
            self.inside.set()

    def let_go(
        self,
    ) -> None:
        self.release.set()
        self._thread.join(WAIT)


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


def test_a_read_only_transaction_begins_read_only() -> None:
    database, script = scripted()

    with database.transaction(read_only=True) as session:
        session.fetchall("SELECT thing_id FROM things")

    assert script.log[1:] == ["BEGIN READ ONLY", "SELECT thing_id FROM things", "COMMIT"]


def test_a_write_in_a_read_only_transaction_becomes_azathoths_error_and_rolls_back() -> None:
    database, script = scripted()

    with (
        pytest.raises(ReadOnlyTransactionError, match="read-only transaction"),
        database.transaction(read_only=True) as session,
    ):
        session.execute("INSERT INTO t VALUES (?)", ("x",))

    assert script.log[-1] == "ROLLBACK"


def test_a_read_only_transaction_after_a_writing_one_on_the_same_connection_reads_only() -> None:
    database, script = scripted()

    with database.transaction() as session:
        session.execute("INSERT INTO t VALUES (?)", ("x",))

    with pytest.raises(ReadOnlyTransactionError), database.transaction(read_only=True) as session:
        session.execute("INSERT INTO t VALUES (?)", ("y",))

    with database.transaction() as session:
        session.execute("INSERT INTO t VALUES (?)", ("z",))

    assert script.log.count("<connect>") == 1


def test_a_read_only_transaction_takes_no_lock() -> None:
    database, script = scripted()

    with (
        pytest.raises(ValueError, match="takes no lock"),
        database.transaction(lock="things", read_only=True),
    ):
        pass

    assert script.log == []
    assert READ_ONLY_LOCK_MESSAGE == (
        "A read-only transaction takes no lock, since it writes nothing."
    )


def test_a_read_only_transaction_is_opened_again_when_its_connection_was_dropped() -> None:
    database, script = scripted(ScriptedConnection([], fail_begin=True))

    with database.transaction(read_only=True):
        pass

    assert script.log == [
        "<connect>",
        "BEGIN READ ONLY",
        "<close>",
        "<connect>",
        "BEGIN READ ONLY",
        "COMMIT",
    ]


def test_psycopg_names_its_read_only_error() -> None:
    psycopg = pytest.importorskip("psycopg")

    from azathoth.persistence.postgres import psycopg_driver

    assert psycopg_driver().read_only_error is psycopg.errors.ReadOnlySqlTransaction


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


# The pool


def test_a_pool_holds_eight_connections_and_waits_half_a_minute_by_default() -> None:
    database, _ = scripted()

    assert DEFAULT_POOL_SIZE == 8
    assert POOL_WAIT_SECONDS == 30.0
    assert database.pool_size == DEFAULT_POOL_SIZE


def test_a_pool_needs_room_for_a_connection_and_a_wait_that_is_not_negative() -> None:
    with pytest.raises(ValueError, match="at least one connection"):
        scripted(pool_size=0)

    with pytest.raises(ValueError, match="cannot wait"):
        scripted(wait_seconds=-1)


def test_transactions_on_two_threads_run_together_on_connections_of_their_own() -> None:
    database, script = scripted()
    first = Holder(database)
    first.inside.wait(WAIT)
    second = Holder(database)
    second.inside.wait(WAIT)

    both_inside = first.inside.is_set() and second.inside.is_set()
    first.let_go()
    second.let_go()

    assert first.failures == second.failures == []
    assert both_inside
    assert len(script.opened) == 2
    assert script.opened[0] is not script.opened[1]


def test_an_idle_connection_is_lent_again_before_another_is_opened() -> None:
    database, script = scripted()
    first = Holder(database)
    first.inside.wait(WAIT)
    second = Holder(database)
    second.inside.wait(WAIT)
    first.let_go()
    second.let_go()

    for _ in range(5):
        with database.transaction() as session:
            session.execute("SELECT 1")

    assert len(script.opened) == 2


def test_a_transaction_that_finds_every_connection_in_use_is_refused_after_waiting() -> None:
    database, script = scripted(pool_size=2, wait_seconds=0.2)
    holders = [Holder(database), Holder(database)]

    for holder in holders:
        holder.inside.wait(WAIT)

    try:
        with pytest.raises(DatabaseBusyError) as raised, database.transaction():
            pass
    finally:
        for holder in holders:
            holder.let_go()

    assert str(raised.value) == (
        "Database postgresql://azathoth@db.example.internal:5432/azathoth had none of its "
        "2 connections free within 0.2 seconds."
    )
    assert len(script.opened) == 2

    with database.transaction():
        pass

    assert len(script.opened) == 2


def test_a_transaction_waiting_for_a_connection_takes_the_one_given_back() -> None:
    database, script = scripted(pool_size=1, wait_seconds=WAIT)
    holder = Holder(database)
    holder.inside.wait(WAIT)
    began = threading.Event()

    def wait_for_it() -> None:
        with database.transaction():
            began.set()

    waiting = threading.Thread(target=wait_for_it)
    waiting.start()

    assert not began.wait(0.2)

    holder.let_go()
    waiting.join(WAIT)

    assert holder.failures == []
    assert began.is_set()
    assert len(script.opened) == 1


def test_a_connection_whose_commit_failed_is_closed_and_its_place_freed() -> None:
    database, script = scripted(ScriptedConnection([], fail_on="COMMIT"), pool_size=1)

    with pytest.raises(DuplicateError), database.transaction() as session:
        session.execute("SELECT 1")

    assert script.opened[0].closed

    with database.transaction():
        pass

    assert len(script.opened) == 2


def test_a_connection_that_could_not_be_opened_frees_its_place() -> None:
    database, script = scripted(pool_size=1, wait_seconds=0, refuse_connects=1)

    with pytest.raises(DroppedError, match="connection refused"), database.transaction():
        pass

    with database.transaction() as session:
        session.execute("SELECT 1")

    assert script.log[0] == "<refused>"
    assert len(script.opened) == 1


def test_a_connection_rolled_back_cleanly_is_kept() -> None:
    database, script = scripted(pool_size=1)

    with pytest.raises(RuntimeError), database.transaction():
        raise RuntimeError("abandon")

    with database.transaction():
        pass

    assert len(script.opened) == 1
    assert not script.opened[0].closed


def test_a_transaction_begun_inside_another_on_one_thread_is_refused() -> None:
    database, script = scripted()

    with database.transaction() as outer:
        with pytest.raises(NestedTransactionError) as raised, database.transaction():
            pass

        outer.execute("SELECT 1")

    assert str(raised.value) == (
        "A transaction was begun inside another on the same thread; "
        "finish the first before beginning the next."
    )
    assert script.log[1:] == ["BEGIN", "SELECT 1", "COMMIT"]

    with database.transaction():
        pass


def test_closing_closes_idle_connections_and_those_in_use_when_given_back() -> None:
    database, script = scripted()
    holder = Holder(database)
    holder.inside.wait(WAIT)

    with database.transaction():
        pass

    database.close()

    assert [connection.closed for connection in script.opened] == [False, True]

    holder.let_go()

    assert holder.failures == []
    assert [connection.closed for connection in script.opened] == [True, True]

    with database.transaction():
        pass

    assert len(script.opened) == 3


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


# Transactions from several threads (ADR 0105)


def test_transactions_from_eight_threads_are_open_at_once(
    postgres_database: PostgresDatabase,
) -> None:
    ready(postgres_database)

    all_inside = threading.Barrier(DEFAULT_POOL_SIZE, timeout=WAIT)
    failures: list[BaseException] = []

    def write(
        index: int,
    ) -> None:
        try:
            with postgres_database.transaction() as session:
                session.execute(
                    "INSERT INTO things (thing_id, count) VALUES (?, ?)",
                    (f"thing-{index}", index),
                )
                all_inside.wait()
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=write, args=(index,)) for index in range(DEFAULT_POOL_SIZE)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert failures == []
    assert sorted(map(str, thing_ids(postgres_database))) == sorted(
        f"thing-{index}" for index in range(DEFAULT_POOL_SIZE)
    )


def test_a_reader_reads_while_a_writer_holds_its_transaction_open(
    postgres_database: PostgresDatabase,
) -> None:
    ready(postgres_database)
    insert(postgres_database, "one")

    writing = threading.Event()
    release = threading.Event()

    def writer() -> None:
        with postgres_database.transaction(lock="things") as session:
            session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("two", 2))
            writing.set()
            release.wait(WAIT)

    thread = threading.Thread(target=writer)
    thread.start()
    writing.wait(WAIT)

    try:
        with postgres_database.transaction(read_only=True) as session:
            seen = session.fetchall("SELECT thing_id FROM things ORDER BY sequence")
    finally:
        release.set()
        thread.join(WAIT)

    assert seen == [("one",)]
    assert thing_ids(postgres_database) == ["one", "two"]


def test_threads_that_prepare_at_once_all_find_the_schema(
    postgres_database: PostgresDatabase,
) -> None:
    postgres_database.initialize(TABLES)
    fresh = PostgresDatabase(postgres_database.location)
    failures: list[BaseException] = []

    def prepare() -> None:
        try:
            fresh.prepare(TABLES)
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=prepare) for _ in range(8)]

    try:
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
    finally:
        fresh.close()

    assert failures == []


def test_a_failed_transaction_in_one_thread_leaves_the_others_turn_intact(
    postgres_database: PostgresDatabase,
) -> None:
    ready(postgres_database)
    insert(postgres_database, "one")

    def collide() -> None:
        with pytest.raises(IntegrityError), postgres_database.transaction() as session:
            session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("one", 1))

    thread = threading.Thread(target=collide)
    thread.start()
    thread.join()

    insert(postgres_database, "two")

    assert thing_ids(postgres_database) == ["one", "two"]

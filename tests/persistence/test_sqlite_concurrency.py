"""Tests that transactions sharing one SQLite file take turns only when they must (ADR 0135)."""

import sqlite3
import threading
from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.persistence.sqlite import BUSY_TIMEOUT_SECONDS, JOURNAL_MODE
from tests.persistence.test_database import TABLES, insert, ready, thing_ids

PERSISTENCE_README = Path(__file__).parents[2] / "src" / "azathoth" / "persistence" / "README.md"

WAIT = 10.0
"""How long a test waits for another thread before it counts as stuck."""


def journal_mode(
    path: Path,
) -> str:
    """Return the journal mode the file keeps."""

    connection = sqlite3.connect(path)

    try:
        row = connection.execute("PRAGMA journal_mode").fetchone()
    finally:
        connection.close()

    return str(row[0])


def test_a_transaction_waits_up_to_half_a_minute_for_another() -> None:
    assert BUSY_TIMEOUT_SECONDS == 30.0


def test_two_transactions_that_read_then_write_both_commit_in_turn(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    ready(SQLiteDatabase(path))

    first_read = threading.Event()
    timeline: list[str] = []
    failures: list[BaseException] = []

    def first() -> None:
        try:
            with SQLiteDatabase(path).transaction() as session:
                session.fetchall("SELECT thing_id FROM things")
                timeline.append("first read")
                first_read.set()
                threading.Event().wait(0.3)
                session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("one", 1))
                timeline.append("first wrote")
        except BaseException as error:
            failures.append(error)

    def second() -> None:
        first_read.wait()

        try:
            with SQLiteDatabase(path).transaction() as session:
                timeline.append("second began")
                session.fetchall("SELECT thing_id FROM things")
                session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("two", 2))
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=first), threading.Thread(target=second)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert failures == []
    assert timeline == ["first read", "first wrote", "second began"]
    assert thing_ids(SQLiteDatabase(path)) == ["one", "two"]


def test_a_lock_still_names_a_table_that_exists_as_an_identifier(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "azathoth.db")
    database.initialize(TABLES)

    with database.transaction(lock="things") as session:
        session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("one", 1))

    assert thing_ids(database) == ["one"]


# The journal


def test_a_new_file_is_kept_in_wal_mode(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    ready(SQLiteDatabase(path))

    assert JOURNAL_MODE == "wal"
    assert journal_mode(path) == "wal"


def test_an_existing_file_is_switched_to_wal_and_keeps_what_it_held(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE kept (name TEXT)")
    connection.execute("INSERT INTO kept VALUES ('before')")
    connection.commit()
    connection.close()

    assert journal_mode(path) == "delete"

    with SQLiteDatabase(path).transaction(read_only=True) as session:
        assert session.fetchall("SELECT name FROM kept") == [("before",)]

    assert journal_mode(path) == "wal"

    with SQLiteDatabase(path).transaction() as session:
        session.execute("INSERT INTO kept VALUES ('after')")

    assert journal_mode(path) == "wal"

    with SQLiteDatabase(path).transaction(read_only=True) as session:
        assert session.fetchall("SELECT name FROM kept") == [("before",), ("after",)]


# Readers and writers


def test_readers_run_together_while_a_writer_holds_the_write_lock(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    ready(SQLiteDatabase(path))
    insert(SQLiteDatabase(path), "one")

    writing = threading.Event()
    release = threading.Event()
    both_reading = threading.Barrier(2, timeout=WAIT)
    seen: list[list[object]] = []
    failures: list[BaseException] = []

    def writer() -> None:
        try:
            with SQLiteDatabase(path).transaction() as session:
                session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("two", 2))
                writing.set()
                release.wait(WAIT)
        except BaseException as error:
            failures.append(error)

    def reader() -> None:
        writing.wait(WAIT)

        try:
            with SQLiteDatabase(path).transaction(read_only=True) as session:
                rows = session.fetchall("SELECT thing_id FROM things ORDER BY sequence")
                both_reading.wait()
                seen.append([row[0] for row in rows])
        except BaseException as error:
            failures.append(error)

    writing_thread = threading.Thread(target=writer)
    readers = [threading.Thread(target=reader) for _ in range(2)]
    writing_thread.start()

    for thread in readers:
        thread.start()

    for thread in readers:
        thread.join()

    release.set()
    writing_thread.join()

    assert failures == []
    assert seen == [["one"], ["one"]]
    assert thing_ids(SQLiteDatabase(path)) == ["one", "two"]


def test_a_writer_commits_while_a_reader_reads_and_the_reader_keeps_its_snapshot(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    ready(SQLiteDatabase(path))
    insert(SQLiteDatabase(path), "one")

    reading = threading.Event()
    committed = threading.Event()
    seen: list[list[object]] = []
    failures: list[BaseException] = []

    def reader() -> None:
        try:
            with SQLiteDatabase(path).transaction(read_only=True) as session:
                before = session.fetchall("SELECT thing_id FROM things ORDER BY sequence")
                reading.set()
                committed.wait(WAIT)
                after = session.fetchall("SELECT thing_id FROM things ORDER BY sequence")
                seen.extend([[row[0] for row in before], [row[0] for row in after]])
        except BaseException as error:
            failures.append(error)

    def writer() -> None:
        reading.wait(WAIT)

        try:
            insert(SQLiteDatabase(path), "two")
            committed.set()
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=reader), threading.Thread(target=writer)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert failures == []
    assert committed.is_set()
    assert seen == [["one"], ["one"]]
    assert thing_ids(SQLiteDatabase(path)) == ["one", "two"]


def test_one_database_shared_by_threads_sets_its_journal_once(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "azathoth.db")
    ready(database)
    failures: list[BaseException] = []

    def read() -> None:
        try:
            for _ in range(20):
                with database.transaction(read_only=True) as session:
                    session.fetchall("SELECT thing_id FROM things")
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=read) for _ in range(8)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert failures == []
    assert journal_mode(database.path) == "wal"


# The documentation


def test_the_readme_says_how_sqlite_transactions_begin() -> None:
    text = PERSISTENCE_README.read_text(encoding="utf-8")

    assert "| SQLite | `BEGIN IMMEDIATE`, as every SQLite transaction that may write is |" in text
    assert "waits up to 30 seconds" in text
    assert "`PRAGMA query_only`" in text
    assert "WAL" in text

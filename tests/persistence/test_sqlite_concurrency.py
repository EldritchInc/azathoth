"""Tests that processes sharing one SQLite file take turns instead of refusing each other."""

import threading
from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.persistence.sqlite import BUSY_TIMEOUT_SECONDS
from tests.persistence.test_database import TABLES, ready, thing_ids

PERSISTENCE_README = Path(__file__).parents[2] / "src" / "azathoth" / "persistence" / "README.md"


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


def test_the_readme_says_every_sqlite_transaction_begins_immediately() -> None:
    text = PERSISTENCE_README.read_text(encoding="utf-8")

    assert "| SQLite | `BEGIN IMMEDIATE`, as every SQLite transaction is |" in text
    assert "waits up to 30 seconds" in text

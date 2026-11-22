"""Contract tests that a transaction is never begun inside another (ADR 0135)."""

import threading

import pytest

from azathoth.persistence import Database, NestedTransactionError, PersistenceError
from tests.persistence.test_database import insert, ready, thing_ids


def test_a_transaction_begun_inside_another_on_one_thread_is_refused(
    database: Database,
) -> None:
    ready(database)

    with database.transaction() as outer:
        with pytest.raises(NestedTransactionError), database.transaction(read_only=True):
            pass

        outer.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("one", 1))

    assert thing_ids(database) == ["one"]


def test_a_refused_nesting_is_a_persistence_error(
    database: Database,
) -> None:
    ready(database)

    with (
        database.transaction(read_only=True),
        pytest.raises(PersistenceError),
        database.transaction(),
    ):
        pass


def test_a_transaction_may_begin_after_another_ends_even_when_the_other_raised(
    database: Database,
) -> None:
    ready(database)

    with pytest.raises(RuntimeError), database.transaction():
        raise RuntimeError("abandon")

    insert(database, "one")

    assert thing_ids(database) == ["one"]


def test_another_thread_may_begin_a_transaction_while_one_is_in_progress(
    database: Database,
) -> None:
    ready(database)
    insert(database, "one")
    seen: list[object] = []
    failures: list[BaseException] = []

    def read() -> None:
        try:
            with database.transaction(read_only=True) as session:
                seen.extend(row[0] for row in session.fetchall("SELECT thing_id FROM things"))
        except BaseException as error:
            failures.append(error)

    with database.transaction(read_only=True):
        thread = threading.Thread(target=read)
        thread.start()
        thread.join(10.0)

    assert failures == []
    assert seen == ["one"]

"""Contract tests of read-only transactions, run on SQLite and PostgreSQL (ADR 0135)."""

import pytest

from azathoth.persistence import (
    Database,
    PersistenceError,
    ReadOnlyTransactionError,
)
from azathoth.persistence.database import READ_ONLY_LOCK_MESSAGE
from tests.persistence.test_database import insert, ready, thing_ids


def test_a_read_only_transaction_reads_what_was_committed(
    database: Database,
) -> None:
    ready(database)
    insert(database, "one", 1)
    insert(database, "two", 2)

    with database.transaction(read_only=True) as session:
        rows = session.fetchall("SELECT thing_id, count FROM things ORDER BY sequence")
        first = session.fetchone("SELECT count FROM things WHERE thing_id = ?", ("two",))

    assert rows == [("one", 1), ("two", 2)]
    assert first == (2,)


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO things (thing_id, count) VALUES ('three', 3)",
        "UPDATE things SET count = 9",
        "DELETE FROM things",
    ],
)
def test_a_read_only_transaction_refuses_every_write_and_keeps_nothing(
    database: Database,
    statement: str,
) -> None:
    ready(database)
    insert(database, "one", 1)

    with pytest.raises(ReadOnlyTransactionError), database.transaction(read_only=True) as session:
        session.execute(statement)

    with database.transaction(read_only=True) as session:
        assert session.fetchall("SELECT thing_id, count FROM things") == [("one", 1)]


def test_a_refused_write_is_a_persistence_error(
    database: Database,
) -> None:
    ready(database)

    with pytest.raises(PersistenceError), database.transaction(read_only=True) as session:
        session.execute("INSERT INTO things (thing_id, count) VALUES ('one', 1)")


def test_a_read_only_transaction_takes_no_lock(
    database: Database,
) -> None:
    ready(database)

    with (
        pytest.raises(ValueError, match="takes no lock"),
        database.transaction(lock="things", read_only=True),
    ):
        pass

    assert str(ValueError(READ_ONLY_LOCK_MESSAGE)) == (
        "A read-only transaction takes no lock, since it writes nothing."
    )


def test_a_block_that_raises_in_a_read_only_transaction_leaves_the_database_usable(
    database: Database,
) -> None:
    ready(database)

    with pytest.raises(RuntimeError), database.transaction(read_only=True):
        raise RuntimeError("abandon")

    insert(database, "one")

    assert thing_ids(database) == ["one"]


def test_a_transaction_after_a_read_only_one_may_write(
    database: Database,
) -> None:
    ready(database)

    with database.transaction(read_only=True) as session:
        session.fetchall("SELECT thing_id FROM things")

    insert(database, "one")

    assert thing_ids(database) == ["one"]

"""Contract tests every database meets, run on SQLite and PostgreSQL (ADR 0102)."""

import pytest

from azathoth.persistence import (
    Database,
    InitializationOutcome,
    IntegrityError,
    Table,
)

THINGS = Table(
    name="things",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS things (
            sequence {sequence},
            thing_id TEXT NOT NULL UNIQUE,
            count INTEGER NOT NULL,
            content {blob},
            payload TEXT
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS things_count ON things (count, sequence)
        """,
    ),
)

REVISIONS = Table(
    name="thing_revisions",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS thing_revisions (
            sequence {sequence},
            thing_id TEXT NOT NULL,
            number INTEGER NOT NULL,
            UNIQUE (thing_id, number)
        )
        """,
    ),
)

TABLES = (THINGS, REVISIONS)

PAYLOAD = '{"b": 1, "a": [true, null], "a": "duplicate keys survive", "ü": "ß"}'


def ready(
    database: Database,
) -> Database:
    """Initialize the database with the test tables, and return it."""

    database.initialize(TABLES)
    database.prepare(TABLES)

    return database


def insert(
    database: Database,
    thing_id: str,
    count: int = 0,
) -> None:
    """Insert one thing in a transaction of its own."""

    with database.transaction() as session:
        session.execute(
            "INSERT INTO things (thing_id, count) VALUES (?, ?)",
            (thing_id, count),
        )


def thing_ids(
    database: Database,
) -> list[object]:
    """Return every thing's ID in insertion order."""

    with database.transaction() as session:
        return [row[0] for row in session.fetchall("SELECT thing_id FROM things ORDER BY sequence")]


# Initializing


def test_initializing_creates_the_tables_once(
    database: Database,
) -> None:
    assert database.initialize(TABLES) is InitializationOutcome.CREATED
    assert database.initialize(TABLES) is InitializationOutcome.CURRENT

    database.prepare(TABLES)

    assert thing_ids(database) == []


def test_initializing_creates_a_table_added_later(
    database: Database,
) -> None:
    database.initialize((THINGS,))

    assert database.initialize(TABLES) is InitializationOutcome.CREATED

    with database.transaction() as session:
        assert session.fetchall("SELECT number FROM thing_revisions") == []


# Values


def test_values_read_back_exactly_as_written(
    database: Database,
) -> None:
    ready(database)

    content = bytes(range(256))

    with database.transaction() as session:
        session.execute(
            "INSERT INTO things (thing_id, count, content, payload) VALUES (?, ?, ?, ?)",
            ("thing-1", 2**31 - 1, content, PAYLOAD),
        )

    with database.transaction() as session:
        row = session.fetchone(
            "SELECT thing_id, count, content, payload FROM things WHERE thing_id = ?",
            ("thing-1",),
        )

    assert row == ("thing-1", 2**31 - 1, content, PAYLOAD)
    assert isinstance(row[2], bytes)


def test_null_reads_back_as_none(
    database: Database,
) -> None:
    ready(database)
    insert(database, "thing-1")

    with database.transaction() as session:
        assert session.fetchone("SELECT content, payload FROM things") == (None, None)


def test_a_boolean_is_stored_as_an_integer(
    database: Database,
) -> None:
    ready(database)

    with database.transaction() as session:
        session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("thing-1", True))

    with database.transaction() as session:
        assert session.fetchone("SELECT count FROM things") == (1,)


def test_a_missing_row_is_none(
    database: Database,
) -> None:
    ready(database)

    with database.transaction() as session:
        assert session.fetchone("SELECT thing_id FROM things WHERE thing_id = ?", ("x",)) is None


def test_percent_and_question_marks_survive_in_literals_and_parameters(
    database: Database,
) -> None:
    ready(database)
    insert(database, "50% off?")
    insert(database, "plain")

    with database.transaction() as session:
        assert session.fetchone("SELECT 'why? 100%'") == ("why? 100%",)
        assert session.fetchall(
            "SELECT thing_id FROM things WHERE thing_id LIKE ? ORDER BY sequence",
            ("50%",),
        ) == [("50% off?",)]
        assert session.fetchall(
            "SELECT thing_id FROM things WHERE thing_id = ?",
            ("50% off?",),
        ) == [("50% off?",)]


# Order


def test_the_sequence_keeps_insertion_order(
    database: Database,
) -> None:
    ready(database)

    for thing_id in ("c", "a", "b"):
        insert(database, thing_id)

    assert thing_ids(database) == ["c", "a", "b"]


# Transactions


def test_a_block_that_raises_rolls_back(
    database: Database,
) -> None:
    ready(database)

    with pytest.raises(RuntimeError), database.transaction() as session:
        session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("thing-1", 0))
        raise RuntimeError("abandon")

    assert thing_ids(database) == []


def test_a_completed_block_commits_every_statement(
    database: Database,
) -> None:
    ready(database)

    with database.transaction() as session:
        session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("a", 0))
        session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("b", 0))

    assert thing_ids(database) == ["a", "b"]


def test_a_duplicate_is_one_integrity_error_and_rolls_back_its_transaction(
    database: Database,
) -> None:
    ready(database)
    insert(database, "thing-1")

    with pytest.raises(IntegrityError), database.transaction() as session:
        session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("thing-2", 0))
        session.execute("INSERT INTO things (thing_id, count) VALUES (?, ?)", ("thing-1", 0))

    assert thing_ids(database) == ["thing-1"]

    insert(database, "thing-3")

    assert thing_ids(database) == ["thing-1", "thing-3"]


def test_an_upsert_inserts_then_updates(
    database: Database,
) -> None:
    ready(database)

    for count in (1, 2):
        with database.transaction() as session:
            session.execute(
                """
                INSERT INTO things (thing_id, count) VALUES (?, ?)
                ON CONFLICT (thing_id) DO UPDATE SET count = excluded.count
                """,
                ("thing-1", count),
            )

    with database.transaction() as session:
        assert session.fetchall("SELECT thing_id, count FROM things") == [("thing-1", 2)]


# Numbering revisions under a lock


def next_revision(
    database: Database,
    thing_id: str,
) -> int:
    """Number and record the next revision of one thing, as revision repositories do."""

    with database.transaction(lock="thing_revisions") as session:
        row = session.fetchone(
            "SELECT COALESCE(MAX(number), 0) FROM thing_revisions WHERE thing_id = ?",
            (thing_id,),
        )

        assert row is not None
        assert isinstance(row[0], int)

        number = row[0] + 1

        session.execute(
            "INSERT INTO thing_revisions (thing_id, number) VALUES (?, ?)",
            (thing_id, number),
        )

    return number


def test_a_locked_transaction_numbers_revisions(
    database: Database,
) -> None:
    ready(database)

    assert [next_revision(database, "thing-1") for _ in range(3)] == [1, 2, 3]
    assert next_revision(database, "thing-2") == 1


def test_a_lock_names_a_table(
    database: Database,
) -> None:
    ready(database)

    with pytest.raises(ValueError, match="is not a table name"):
        database.transaction(lock="thing_revisions; DROP TABLE things")


def test_closing_and_using_again_reopens(
    database: Database,
) -> None:
    ready(database)
    insert(database, "thing-1")

    database.close()

    assert thing_ids(database) == ["thing-1"]

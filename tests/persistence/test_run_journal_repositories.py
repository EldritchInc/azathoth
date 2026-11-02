"""Contract tests every run journal repository meets, in memory, SQLite and PostgreSQL."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from azathoth.persistence import Database, SQLiteDatabase
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import (
    RUN_JOURNAL_TABLES,
    InMemoryRunJournalRepository,
    RunJournalPositionTakenError,
    RunJournalRepository,
    SqlRunJournalRepository,
)
from tests.persistence.conftest import BACKENDS
from tests.workflows.test_run_journal import (
    EVENTS,
    INVOCATION_ID,
    OTHER_RUN_ID,
    RUN_ID,
    entry,
)


@pytest.fixture(params=("memory", *BACKENDS))
def journal(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[RunJournalRepository]:
    """Return an empty repository of each kind in turn, over each database."""

    if request.param == "memory":
        yield InMemoryRunJournalRepository()
        return

    database: Database = (
        SQLiteDatabase(tmp_path / "azathoth.db")
        if request.param == "sqlite"
        else request.getfixturevalue("postgres_database")
    )

    database.initialize(RUN_JOURNAL_TABLES)

    yield SqlRunJournalRepository(database)


def test_a_run_with_no_journal_has_no_entries(
    journal: RunJournalRepository,
) -> None:
    assert journal.entries(RUN_ID) == ()


def test_entries_come_back_whole_and_in_position_order(
    journal: RunJournalRepository,
) -> None:
    recorded = [
        entry(event, position=position, invocation_id=INVOCATION_ID)
        for position, event in enumerate(EVENTS, start=1)
    ]

    for item in (recorded[2], recorded[0], recorded[4], recorded[1], recorded[3]):
        journal.append(item)

    assert journal.entries(RUN_ID) == tuple(recorded)


def test_each_run_has_its_own_journal(
    journal: RunJournalRepository,
) -> None:
    journal.append(entry(EVENTS[0], position=1))
    journal.append(entry(EVENTS[0], position=1, run_id=OTHER_RUN_ID))
    journal.append(entry(EVENTS[1], position=2, run_id=OTHER_RUN_ID))

    assert [item.position for item in journal.entries(RUN_ID)] == [1]
    assert [item.position for item in journal.entries(OTHER_RUN_ID)] == [1, 2]


def test_a_position_is_recorded_once(
    journal: RunJournalRepository,
) -> None:
    journal.append(entry(EVENTS[0], position=1))

    with pytest.raises(RunJournalPositionTakenError) as error:
        journal.append(entry(EVENTS[1], position=1))

    assert str(error.value) == f"Run {RUN_ID} already records journal position 1."
    assert journal.entries(RUN_ID) == (entry(EVENTS[0], position=1),)


def test_an_invocations_run_is_found_by_its_journal(
    journal: RunJournalRepository,
) -> None:
    journal.append(entry(EVENTS[0], position=1, invocation_id=INVOCATION_ID))
    journal.append(entry(EVENTS[1], position=2, invocation_id=INVOCATION_ID))
    journal.append(entry(EVENTS[0], position=1, run_id=OTHER_RUN_ID))

    assert journal.invocation_run_id(INVOCATION_ID) == RUN_ID


def test_an_invocation_with_no_journal_has_no_run(
    journal: RunJournalRepository,
) -> None:
    journal.append(entry(EVENTS[0], position=1))

    assert journal.invocation_run_id(INVOCATION_ID) is None


def test_the_repositories_journal_runs_in_the_database_they_open(
    tmp_path: Path,
) -> None:
    repositories = open_repositories(tmp_path / "azathoth.db")

    repositories.run_journal.append(entry(EVENTS[0], position=1))

    assert isinstance(repositories.run_journal, SqlRunJournalRepository)
    assert open_repositories(tmp_path / "azathoth.db").run_journal.entries(RUN_ID) == (
        entry(EVENTS[0], position=1),
    )

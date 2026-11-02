"""Contract tests every child-run index meets, in memory, SQLite and PostgreSQL (ADR 0105)."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.context import child_lineage
from azathoth.persistence import Database, SQLiteDatabase
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import (
    RUN_CHILD_TABLES,
    InMemoryRunChildRepository,
    RunChild,
    RunChildRepository,
    SqlRunChildRepository,
)
from tests.persistence.conftest import BACKENDS
from tests.workflows.test_run_children import AT, PARENT_STEP
from tests.workflows.test_runner_journal import INVOCATION_ID, WORKFLOW_ID


@pytest.fixture(params=("memory", *BACKENDS))
def children(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[RunChildRepository]:
    """Return an empty index of each kind in turn, over each database."""

    if request.param == "memory":
        yield InMemoryRunChildRepository()
        return

    database: Database = (
        SQLiteDatabase(tmp_path / "azathoth.db")
        if request.param == "sqlite"
        else request.getfixturevalue("postgres_database")
    )

    database.initialize(RUN_CHILD_TABLES)

    yield SqlRunChildRepository(database)


def child(
    number: int,
    *,
    invocation_id: UUID | None = None,
) -> RunChild:
    """Return the index entry of one child of the parent step."""

    return RunChild.of(
        child_lineage(PARENT_STEP, workflow_id=WORKFLOW_ID),
        run_id=UUID(int=number),
        workflow_id=WORKFLOW_ID,
        invocation_id=invocation_id,
        recorded_at=AT + timedelta(seconds=number),
    )


def test_a_run_with_no_children_has_none(
    children: RunChildRepository,
) -> None:
    assert children.children_of(PARENT_STEP.step.run_id) == ()


def test_children_come_back_whole_in_the_order_they_started(
    children: RunChildRepository,
) -> None:
    recorded = [child(3, invocation_id=INVOCATION_ID), child(1), child(2)]

    for entry in recorded:
        children.record(entry)

    assert children.children_of(PARENT_STEP.step.run_id) == tuple(recorded)


def test_a_child_is_recorded_once(
    children: RunChildRepository,
) -> None:
    children.record(child(1))
    children.record(child(1, invocation_id=INVOCATION_ID))

    assert children.children_of(PARENT_STEP.step.run_id) == (child(1),)


def test_another_runs_children_are_not_this_ones(
    children: RunChildRepository,
) -> None:
    children.record(child(1))

    assert children.children_of(PARENT_STEP.root.run_id) == ()


def test_the_repositories_index_children_in_the_database_they_open(
    tmp_path: Path,
) -> None:
    open_repositories(tmp_path / "azathoth.db").run_children.record(child(1))

    assert open_repositories(tmp_path / "azathoth.db").run_children.children_of(
        PARENT_STEP.step.run_id
    ) == (child(1),)

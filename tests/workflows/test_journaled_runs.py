"""Tests that a run journal lists a workflow's journaled runs, newest first (ADR 0129)."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from azathoth.context import Context
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    JournalRunResumed,
    JournalRunStarted,
    RunJournalEntry,
    RunJournalRepository,
    WorkflowMetadata,
)

WORKFLOW_ID = UUID("c1910000-0000-4000-8000-000000000001")

OTHER_WORKFLOW_ID = UUID("c1910000-0000-4000-8000-000000000002")

STARTED_AT = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def started(
    journal: RunJournalRepository,
    workflow_id: UUID,
) -> UUID:
    """Journal one run of a workflow starting, and resuming once; return its ID."""

    run_id = uuid4()
    workflow = WorkflowMetadata(
        id=workflow_id,
        name="journaled",
        description="A journaled workflow.",
        version="1.0.0",
    )

    journal.append(
        RunJournalEntry(
            run_id=run_id,
            position=1,
            workflow_id=workflow_id,
            recorded_at=STARTED_AT,
            event=JournalRunStarted(
                workflow=workflow,
                initial_context=Context(),
                started_at=STARTED_AT,
            ),
        )
    )
    journal.append(
        RunJournalEntry(
            run_id=run_id,
            position=2,
            workflow_id=workflow_id,
            recorded_at=STARTED_AT,
            event=JournalRunResumed(resumed_at=STARTED_AT),
        )
    )

    return run_id


@pytest.fixture(params=["memory", "sqlite"])
def journal(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> RunJournalRepository:
    """Return an empty journal of each kind."""

    if request.param == "memory":
        return InMemoryRunJournalRepository()

    return open_repositories(tmp_path / "azathoth.db").run_journal


def test_a_workflows_journaled_runs_are_listed_newest_first_once_each(
    journal: RunJournalRepository,
) -> None:
    first = started(journal, WORKFLOW_ID)
    started(journal, OTHER_WORKFLOW_ID)
    second = started(journal, WORKFLOW_ID)

    assert journal.journaled_runs(WORKFLOW_ID) == (second, first)


def test_a_workflow_with_no_journal_has_no_journaled_runs(
    journal: RunJournalRepository,
) -> None:
    started(journal, OTHER_WORKFLOW_ID)

    assert journal.journaled_runs(WORKFLOW_ID) == ()

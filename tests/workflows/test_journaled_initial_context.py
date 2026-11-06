"""Tests for reading a run's initial context from its journal, for tools' content (ADR 0114)."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from azathoth.context import Context, ContextEvent
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    JournalAttemptStarted,
    JournalRunStarted,
    RunJournalEntry,
    WorkflowMetadata,
    journaled_initial_context,
)

RUN_ID = UUID("c1300000-0000-4000-8000-000000000001")

OTHER_RUN_ID = UUID("c1300000-0000-4000-8000-000000000002")

WORKFLOW = WorkflowMetadata(
    id=UUID("c1300000-0000-4000-8000-000000000003"),
    name="Hash a document",
    description="Hash the workflow's document.",
    version="1.0.0",
)

AT = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)

CONTEXT = Context(
    events=(
        ContextEvent(
            event_type="workflow.input.received",
            payload={"input": "the old ones wait"},
            producer="azathoth.cli",
            occurred_at=AT,
        ),
    )
)


def entry(
    position: int,
    event: JournalRunStarted | JournalAttemptStarted,
    *,
    run_id: UUID = RUN_ID,
) -> RunJournalEntry:
    """Return one entry of a run's journal."""

    return RunJournalEntry(
        run_id=run_id,
        position=position,
        workflow_id=WORKFLOW.id,
        recorded_at=AT,
        event=event,
    )


def started() -> JournalRunStarted:
    """Return the start of the test run, from the test context."""

    return JournalRunStarted(workflow=WORKFLOW, initial_context=CONTEXT, started_at=AT)


def test_a_journal_gives_the_context_its_run_started_from() -> None:
    journal = InMemoryRunJournalRepository()
    journal.append(entry(1, started()))
    journal.append(
        entry(
            2,
            JournalAttemptStarted(
                step_id=UUID("c1300000-0000-4000-8000-000000000004"),
                layer_index=0,
                attempt_number=1,
                started_at=AT,
            ),
        )
    )

    assert journaled_initial_context(journal, RUN_ID) == CONTEXT


def test_a_run_without_a_journal_has_no_known_initial_context() -> None:
    journal = InMemoryRunJournalRepository()
    journal.append(entry(1, started(), run_id=OTHER_RUN_ID))

    assert journaled_initial_context(journal, RUN_ID) is None


def test_a_journal_that_does_not_begin_with_the_runs_start_gives_nothing() -> None:
    journal = InMemoryRunJournalRepository()
    journal.append(
        entry(
            1,
            JournalAttemptStarted(
                step_id=UUID("c1300000-0000-4000-8000-000000000004"),
                layer_index=0,
                attempt_number=1,
                started_at=AT,
            ),
        )
    )

    assert journaled_initial_context(journal, RUN_ID) is None


def test_a_databases_tool_content_reads_its_store_and_its_journal(
    tmp_path: Path,
) -> None:
    repositories = open_repositories(tmp_path / "azathoth.db")
    repositories.run_journal.append(entry(1, started()))
    digest = repositories.content.put(b"%PDF-1.7")

    content = repositories.tool_content

    assert content.store.get(digest) == b"%PDF-1.7"
    assert content.initial_context(RUN_ID) == CONTEXT
    assert content.initial_context(OTHER_RUN_ID) is None

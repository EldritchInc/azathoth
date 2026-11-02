"""Tests that a child run is indexed under the run whose step started it (ADR 0105)."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.context import (
    Context,
    LineageRun,
    LineageStep,
    StepLineage,
    child_lineage,
    create_lineage_event,
)
from azathoth.workflows import (
    InMemoryRunChildRepository,
    InMemoryRunJournalRepository,
    RunChild,
    WorkflowRunner,
)
from tests.workflows.test_run_resume import Counted, Crash, CrashingJournal
from tests.workflows.test_runner_journal import (
    FIRST_STEP_ID,
    INVOCATION_ID,
    WORKFLOW_ID,
    candidate,
    step,
)

PARENT_STEP = StepLineage(
    step=LineageStep(
        workflow_id=UUID("c1900000-0000-4000-8000-000000000001"),
        run_id=UUID("c1900000-0000-4000-8000-000000000002"),
        step_id=UUID("c1900000-0000-4000-8000-000000000003"),
        attempt=2,
    ),
    depth=1,
    root=LineageRun(
        workflow_id=UUID("c1900000-0000-4000-8000-000000000011"),
        run_id=UUID("c1900000-0000-4000-8000-000000000012"),
    ),
)

AT = datetime(2026, 11, 1, 22, 30, tzinfo=UTC)

CHILD_CONTEXT = Context(
    events=(create_lineage_event(child_lineage(PARENT_STEP, workflow_id=WORKFLOW_ID)),)
)


def test_a_child_names_its_parent_step_attempt_and_root() -> None:
    child = RunChild.of(
        child_lineage(PARENT_STEP, workflow_id=WORKFLOW_ID),
        run_id=UUID(int=5),
        workflow_id=WORKFLOW_ID,
        invocation_id=INVOCATION_ID,
        recorded_at=AT,
    )

    assert child == RunChild(
        child_run_id=UUID(int=5),
        child_workflow_id=WORKFLOW_ID,
        child_invocation_id=INVOCATION_ID,
        parent_run_id=PARENT_STEP.step.run_id,
        parent_step_id=PARENT_STEP.step.step_id,
        parent_attempt=2,
        root_run_id=PARENT_STEP.root.run_id,
        depth=2,
        recorded_at=AT,
    )


def test_the_runner_indexes_a_child_run_under_its_parent_as_it_starts() -> None:
    children = InMemoryRunChildRepository()

    run = asyncio.run(
        WorkflowRunner(children=children).run(
            candidate(step(FIRST_STEP_ID, Counted("first"))),
            CHILD_CONTEXT,
            invocation_id=INVOCATION_ID,
        )
    )

    (child,) = children.children_of(PARENT_STEP.step.run_id)

    assert child.child_run_id == run.id
    assert child.child_invocation_id == INVOCATION_ID
    assert (child.parent_step_id, child.parent_attempt, child.depth) == (
        PARENT_STEP.step.step_id,
        2,
        2,
    )


def test_a_root_run_is_nobodys_child() -> None:
    children = InMemoryRunChildRepository()

    asyncio.run(
        WorkflowRunner(children=children).run(
            candidate(step(FIRST_STEP_ID, Counted("first"))),
            Context(),
        )
    )

    assert children.children_of(PARENT_STEP.step.run_id) == ()


def test_a_resumed_child_is_indexed_once() -> None:
    children = InMemoryRunChildRepository()
    journal = CrashingJournal()
    journal.crash("attempt.finished")
    workflow = candidate(step(FIRST_STEP_ID, Counted("first")))

    with pytest.raises(Crash):
        asyncio.run(WorkflowRunner(journal=journal, children=children).run(workflow, CHILD_CONTEXT))

    (run_id,) = journal.run_ids

    asyncio.run(WorkflowRunner(journal=journal, children=children).resume(workflow, run_id=run_id))

    assert [child.child_run_id for child in children.children_of(PARENT_STEP.step.run_id)] == [
        run_id
    ]


def test_recording_a_child_again_keeps_the_first_record() -> None:
    children = InMemoryRunChildRepository()
    first = RunChild.of(
        child_lineage(PARENT_STEP, workflow_id=WORKFLOW_ID),
        run_id=UUID(int=5),
        workflow_id=WORKFLOW_ID,
        invocation_id=None,
        recorded_at=AT,
    )

    children.record(first)
    children.record(first.model_copy(update={"child_invocation_id": INVOCATION_ID}))

    assert children.children_of(PARENT_STEP.step.run_id) == (first,)


def test_a_journal_is_not_needed_to_index_children() -> None:
    children = InMemoryRunChildRepository()

    asyncio.run(
        WorkflowRunner(journal=InMemoryRunJournalRepository(), children=children).run(
            candidate(step(FIRST_STEP_ID, Counted("first"))),
            CHILD_CONTEXT,
        )
    )

    assert len(children.children_of(PARENT_STEP.step.run_id)) == 1

"""Tests for SQLite workflow run evidence persistence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.context import Context, ContextEvent
from azathoth.execution import ExecutionResult
from azathoth.workflows import (
    SQLiteWorkflowRunRepository,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunRepository,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepStatus,
    WorkflowValue,
    require_workflow_run_repository,
)

RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_RUN_ID = UUID("22222222-2222-2222-2222-222222222222")

WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

STEP_ID = UUID("55555555-5555-5555-5555-555555555555")
STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")

INITIAL_EVENT_ID = UUID("77777777-7777-7777-7777-777777777777")
COMPLETED_EVENT_ID = UUID("88888888-8888-8888-8888-888888888888")

STARTED_AT = datetime(
    2026,
    8,
    18,
    12,
    0,
    tzinfo=UTC,
)
COMPLETED_AT = datetime(
    2026,
    8,
    18,
    12,
    0,
    1,
    tzinfo=UTC,
)


def create_initial_context() -> Context:
    """Create deterministic workflow input context."""

    return Context(
        events=(
            ContextEvent(
                id=INITIAL_EVENT_ID,
                event_type="request.received",
                payload={
                    "text": "one two three four",
                },
                producer="test",
                occurred_at=STARTED_AT,
            ),
        ),
    )


def create_final_context() -> Context:
    """Create deterministic workflow final context."""

    return create_initial_context().append(
        ContextEvent(
            id=COMPLETED_EVENT_ID,
            event_type="workflow.test.completed",
            payload={
                "result": "success",
            },
            producer="test",
            occurred_at=COMPLETED_AT,
        )
    )


def create_execution() -> ExecutionResult:
    """Create deterministic strategy execution evidence."""

    initial_context = create_initial_context()

    return ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="test strategy",
        strategy_version="1.0.0",
        output={
            "classification": "positive",
        },
        initial_context=initial_context,
        final_context=create_final_context(),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def create_run(
    *,
    run_id: UUID = RUN_ID,
    workflow_id: UUID = WORKFLOW_ID,
    workflow_name: str = "test workflow",
) -> WorkflowRun:
    """Create complete deterministic workflow run evidence."""

    execution = create_execution()

    attempt = WorkflowStepAttempt(
        attempt_number=1,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        execution=execution,
    )

    step = WorkflowStepRun(
        step_id=STEP_ID,
        layer_index=0,
        status=WorkflowStepStatus.EXECUTED,
        execution=execution,
        attempts=(attempt,),
        values=(
            WorkflowValue(
                name="classification",
                value="positive",
                producer_step_id=STEP_ID,
            ),
        ),
    )

    return WorkflowRun(
        id=run_id,
        workflow=WorkflowMetadata(
            id=workflow_id,
            name=workflow_name,
            description="Exercise SQLite workflow run evidence.",
            version="1.0.0",
        ),
        steps=(step,),
        initial_context=create_initial_context(),
        final_context=create_final_context(),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def test_sqlite_run_repository_saves_and_gets_run(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunRepository(tmp_path / "evidence.db")
    run = create_run()

    repository.save(run)

    restored = repository.get(RUN_ID)

    assert restored == run
    assert restored is not run


def test_sqlite_run_repository_returns_none_for_unknown_run(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunRepository(tmp_path / "evidence.db")

    assert repository.get(RUN_ID) is None


def test_sqlite_run_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunRepository(tmp_path / "evidence.db")

    first = create_run()

    second = create_run(
        run_id=SECOND_RUN_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
    )

    repository.save(first)
    repository.save(second)

    assert repository.runs() == (
        first,
        second,
    )


def test_sqlite_run_repository_rejects_duplicate_run(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunRepository(tmp_path / "evidence.db")
    run = create_run()

    repository.save(run)

    with pytest.raises(
        ValueError,
        match=f"Workflow run {RUN_ID} already exists",
    ):
        repository.save(run)


def test_sqlite_run_repository_filters_by_workflow(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunRepository(tmp_path / "evidence.db")

    first = create_run()

    second = create_run(
        run_id=SECOND_RUN_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        workflow_name="second workflow",
    )

    repository.save(first)
    repository.save(second)

    assert repository.runs_for_workflow(WORKFLOW_ID) == (first,)

    assert repository.runs_for_workflow(SECOND_WORKFLOW_ID) == (second,)


def test_sqlite_run_repository_returns_empty_tuple_for_unknown_workflow(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunRepository(tmp_path / "evidence.db")

    repository.save(create_run())

    assert repository.runs_for_workflow(SECOND_WORKFLOW_ID) == ()


def test_sqlite_run_repository_reconstructs_complete_execution_evidence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.db"

    run = create_run()

    SQLiteWorkflowRunRepository(database).save(run)

    restored = SQLiteWorkflowRunRepository(database).get(RUN_ID)

    assert restored == run
    assert restored is not run
    assert restored is not None

    assert restored.id == RUN_ID
    assert restored.workflow.id == WORKFLOW_ID

    assert restored.initial_context == create_initial_context()
    assert restored.final_context == create_final_context()

    assert len(restored.steps) == 1

    step = restored.steps[0]

    assert step.step_id == STEP_ID
    assert step.status is WorkflowStepStatus.EXECUTED

    assert step.execution == create_execution()

    assert len(step.attempts) == 1
    assert step.attempts[0].execution == create_execution()

    assert step.values == (
        WorkflowValue(
            name="classification",
            value="positive",
            producer_step_id=STEP_ID,
        ),
    )

    assert restored.started_at == STARTED_AT
    assert restored.completed_at == COMPLETED_AT


def test_sqlite_run_repository_preserves_derived_evidence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.db"

    run = create_run()

    SQLiteWorkflowRunRepository(database).save(run)

    restored = SQLiteWorkflowRunRepository(database).get(RUN_ID)

    assert restored is not None

    assert restored.statistics == run.statistics
    assert restored.reliability == run.reliability
    assert restored.succeeded is run.succeeded
    assert restored.duration_seconds == run.duration_seconds
    assert restored.total_attempt_count == run.total_attempt_count


def test_sqlite_run_repository_survives_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.db"

    run = create_run()

    first_repository = SQLiteWorkflowRunRepository(database)

    first_repository.save(run)

    reconstructed_repository = SQLiteWorkflowRunRepository(database)

    assert reconstructed_repository.runs() == (run,)


def test_sqlite_run_repository_satisfies_repository_protocol(
    tmp_path: Path,
) -> None:
    repository: WorkflowRunRepository = require_workflow_run_repository(
        SQLiteWorkflowRunRepository(tmp_path / "evidence.db")
    )

    run = create_run()

    repository.save(run)

    assert repository.get(RUN_ID) == run

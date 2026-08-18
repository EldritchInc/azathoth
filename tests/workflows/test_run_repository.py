"""Tests for durable workflow run evidence repositories."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows import (
    InMemoryWorkflowRunRepository,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunRepository,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepStatus,
    require_workflow_run_repository,
)

RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_RUN_ID = UUID("22222222-2222-2222-2222-222222222222")

WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

STEP_ID = UUID("55555555-5555-5555-5555-555555555555")
STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")

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


def create_execution() -> ExecutionResult:
    """Create deterministic strategy execution evidence."""

    context = Context()

    return ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="test strategy",
        strategy_version="1.0.0",
        output="success",
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def create_run(
    *,
    run_id: UUID = RUN_ID,
    workflow_id: UUID = WORKFLOW_ID,
    workflow_name: str = "test workflow",
) -> WorkflowRun:
    """Create deterministic workflow run evidence."""

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
    )

    return WorkflowRun(
        id=run_id,
        workflow=WorkflowMetadata(
            id=workflow_id,
            name=workflow_name,
            description="Exercise durable workflow run evidence.",
            version="1.0.0",
        ),
        steps=(step,),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def test_workflow_run_records_stable_identifier() -> None:
    run = create_run()

    assert run.id == RUN_ID


def test_workflow_run_identifier_round_trips_through_json() -> None:
    run = create_run()

    restored = WorkflowRun.model_validate_json(run.model_dump_json())

    assert restored == run
    assert restored.id == RUN_ID


def test_in_memory_run_repository_saves_and_gets_run() -> None:
    repository = InMemoryWorkflowRunRepository()
    run = create_run()

    repository.save(run)

    assert repository.get(RUN_ID) is run


def test_in_memory_run_repository_returns_none_for_unknown_run() -> None:
    repository = InMemoryWorkflowRunRepository()

    assert repository.get(RUN_ID) is None


def test_in_memory_run_repository_preserves_insertion_order() -> None:
    repository = InMemoryWorkflowRunRepository()

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


def test_in_memory_run_repository_rejects_duplicate_run() -> None:
    repository = InMemoryWorkflowRunRepository()
    run = create_run()

    repository.save(run)

    with pytest.raises(
        ValueError,
        match=f"Workflow run {RUN_ID} already exists",
    ):
        repository.save(run)


def test_in_memory_run_repository_filters_by_workflow() -> None:
    repository = InMemoryWorkflowRunRepository()

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


def test_in_memory_run_repository_returns_empty_tuple_for_unknown_workflow() -> None:
    repository = InMemoryWorkflowRunRepository()

    repository.save(create_run())

    assert repository.runs_for_workflow(SECOND_WORKFLOW_ID) == ()


def test_run_repository_preserves_complete_execution_evidence() -> None:
    repository = InMemoryWorkflowRunRepository()
    run = create_run()

    repository.save(run)

    restored = repository.get(RUN_ID)

    assert restored is run

    assert restored.workflow.id == WORKFLOW_ID
    assert restored.steps[0].status is WorkflowStepStatus.EXECUTED
    assert restored.steps[0].execution == create_execution()
    assert restored.steps[0].attempts[0].execution == create_execution()
    assert restored.started_at == STARTED_AT
    assert restored.completed_at == COMPLETED_AT


def test_in_memory_run_repository_satisfies_repository_protocol() -> None:
    repository: WorkflowRunRepository = require_workflow_run_repository(
        InMemoryWorkflowRunRepository()
    )

    run = create_run()

    repository.save(run)

    assert repository.get(RUN_ID) == run

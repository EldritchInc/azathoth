"""Tests for recorded workflow execution results."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows import WorkflowMetadata, WorkflowRun, WorkflowStepRun, WorkflowValue

WORKFLOW_ID = UUID("9af3990b-a801-47f8-b9e4-733cbdf8b635")
STEP_ONE_ID = UUID("ef169ce8-3eab-48ef-b6f3-d32be6c52f95")
STEP_TWO_ID = UUID("e74edb3a-8229-480d-91ef-7cbd0e4a88db")

STRATEGY_ONE_ID = UUID("152bf0b4-3bbc-4aaa-9959-79fd09c41904")
STRATEGY_TWO_ID = UUID("cb04e136-f865-4528-8651-8bbfdb6ec101")


def create_execution_result(
    *,
    strategy_id: UUID,
    strategy_name: str,
    context: Context,
) -> ExecutionResult:
    """Create a deterministic strategy execution result."""

    started_at = datetime(
        2026,
        8,
        6,
        22,
        0,
        tzinfo=UTC,
    )
    completed_at = datetime(
        2026,
        8,
        6,
        22,
        0,
        1,
        tzinfo=UTC,
    )

    return ExecutionResult(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        strategy_version="1.0.0",
        output=None,
        initial_context=context,
        final_context=context,
        started_at=started_at,
        completed_at=completed_at,
    )


def create_workflow_run() -> WorkflowRun:
    """Create a deterministic recorded workflow run."""

    context = Context()

    return WorkflowRun(
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Support workflow",
            description="Classify and resolve a support request.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ONE_ID,
                layer_index=0,
                execution=create_execution_result(
                    strategy_id=STRATEGY_ONE_ID,
                    strategy_name="Classifier",
                    context=context,
                ),
                values=(
                    WorkflowValue(
                        name="classification",
                        value="support",
                        producer_step_id=STEP_ONE_ID,
                    ),
                ),
            ),
            WorkflowStepRun(
                step_id=STEP_TWO_ID,
                layer_index=1,
                execution=create_execution_result(
                    strategy_id=STRATEGY_TWO_ID,
                    strategy_name="Reasoner",
                    context=context,
                ),
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=datetime(
            2026,
            8,
            6,
            22,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            8,
            6,
            22,
            0,
            2,
            tzinfo=UTC,
        ),
    )


def test_workflow_run_records_workflow_and_step_executions() -> None:
    run = create_workflow_run()

    assert run.workflow.id == WORKFLOW_ID
    assert tuple(step.step_id for step in run.steps) == (
        STEP_ONE_ID,
        STEP_TWO_ID,
    )
    assert tuple(step.layer_index for step in run.steps) == (
        0,
        1,
    )
    assert tuple(step.execution.strategy_id for step in run.steps) == (
        STRATEGY_ONE_ID,
        STRATEGY_TWO_ID,
    )


def test_workflow_step_identity_is_distinct_from_strategy_identity() -> None:
    run = create_workflow_run()

    first = run.steps[0]

    assert first.step_id == STEP_ONE_ID
    assert first.execution.strategy_id == STRATEGY_ONE_ID
    assert first.step_id != first.execution.strategy_id


def test_workflow_run_requires_at_least_one_step() -> None:
    context = Context()

    with pytest.raises(ValidationError):
        WorkflowRun(
            workflow=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="Empty workflow",
                description="An invalid empty workflow run.",
            ),
            steps=(),
            initial_context=context,
            final_context=context,
            started_at=datetime(
                2026,
                8,
                6,
                22,
                0,
                tzinfo=UTC,
            ),
            completed_at=datetime(
                2026,
                8,
                6,
                22,
                0,
                tzinfo=UTC,
            ),
        )


def test_workflow_run_rejects_completion_before_start() -> None:
    context = Context()

    with pytest.raises(
        ValidationError,
        match="cannot precede",
    ):
        WorkflowRun(
            workflow=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="Invalid timing",
                description="A workflow with invalid timestamps.",
            ),
            steps=(
                WorkflowStepRun(
                    step_id=STEP_ONE_ID,
                    layer_index=0,
                    execution=create_execution_result(
                        strategy_id=STRATEGY_ONE_ID,
                        strategy_name="Classifier",
                        context=context,
                    ),
                ),
            ),
            initial_context=context,
            final_context=context,
            started_at=datetime(
                2026,
                8,
                6,
                22,
                0,
                2,
                tzinfo=UTC,
            ),
            completed_at=datetime(
                2026,
                8,
                6,
                22,
                0,
                tzinfo=UTC,
            ),
        )


def test_workflow_run_is_immutable() -> None:
    run = create_workflow_run()

    with pytest.raises(ValidationError):
        run.steps = ()


def test_workflow_run_round_trips_through_json() -> None:
    run = create_workflow_run()

    restored = WorkflowRun.model_validate_json(run.model_dump_json())

    assert restored == run


def test_workflow_step_run_records_workflow_values() -> None:
    run = create_workflow_run()

    assert tuple(value.name for value in run.steps[0].values) == ("classification",)

    assert run.steps[0].values[0].value == "support"

    assert run.steps[1].values == ()

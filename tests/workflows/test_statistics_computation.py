"""Tests for computing workflow execution statistics."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRun,
    WorkflowStepAttempt,
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("11757f68-90e0-4f5d-b88c-a011c06bcab1")

STEP_ONE_ID = UUID("bd9b4f11-84eb-4bea-a006-98f5140cb268")
STEP_TWO_ID = UUID("b905fe27-464b-43e7-a45e-2a02ef501933")
STEP_THREE_ID = UUID("38bdfe6d-cdea-4485-83c5-8a82f49d86a4")

STRATEGY_ONE_ID = UUID("d0821e14-a733-46f7-b89e-1765100f8330")
STRATEGY_TWO_ID = UUID("19ebfca2-d3d4-48f0-91eb-a26ca0b60f0c")

STARTED_AT = datetime(
    2026,
    8,
    11,
    13,
    30,
    tzinfo=UTC,
)

COMPLETED_AT = datetime(
    2026,
    8,
    11,
    13,
    30,
    5,
    tzinfo=UTC,
)


def create_execution(
    *,
    strategy_id: UUID,
    name: str,
) -> ExecutionResult:
    """Create a deterministic successful execution result."""

    context = Context()

    return ExecutionResult(
        strategy_id=strategy_id,
        strategy_name=name,
        strategy_version="1.0.0",
        output=name,
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def create_successful_attempt(
    *,
    attempt_number: int,
    execution: ExecutionResult,
) -> WorkflowStepAttempt:
    """Create a successful workflow execution attempt."""

    return WorkflowStepAttempt(
        attempt_number=attempt_number,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        execution=execution,
    )


def create_failed_attempt(
    *,
    attempt_number: int,
) -> WorkflowStepAttempt:
    """Create a failed workflow execution attempt."""

    return WorkflowStepAttempt(
        attempt_number=attempt_number,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        failure=WorkflowStepFailure(
            exception_type="RuntimeError",
            message="temporary failure",
        ),
    )


def create_run() -> WorkflowRun:
    """Create a workflow run containing executed, failed, and skipped steps."""

    first_execution = create_execution(
        strategy_id=STRATEGY_ONE_ID,
        name="First",
    )

    second_execution = create_execution(
        strategy_id=STRATEGY_TWO_ID,
        name="Second",
    )

    return WorkflowRun(
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Statistics workflow",
            description="Compute workflow execution statistics.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ONE_ID,
                layer_index=0,
                status=WorkflowStepStatus.EXECUTED,
                execution=first_execution,
                attempts=(
                    create_successful_attempt(
                        attempt_number=1,
                        execution=first_execution,
                    ),
                ),
            ),
            WorkflowStepRun(
                step_id=STEP_TWO_ID,
                layer_index=1,
                status=WorkflowStepStatus.EXECUTED,
                execution=second_execution,
                attempts=(
                    create_failed_attempt(
                        attempt_number=1,
                    ),
                    create_failed_attempt(
                        attempt_number=2,
                    ),
                    create_successful_attempt(
                        attempt_number=3,
                        execution=second_execution,
                    ),
                ),
            ),
            WorkflowStepRun(
                step_id=STEP_THREE_ID,
                layer_index=1,
                status=WorkflowStepStatus.SKIPPED,
                execution=None,
                attempts=(),
                values=(),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def test_statistics_count_workflow_steps() -> None:
    statistics = create_run().statistics

    assert statistics.total_steps == 3
    assert statistics.executed_steps == 2
    assert statistics.failed_steps == 0
    assert statistics.skipped_steps == 1


def test_statistics_count_attempts() -> None:
    statistics = create_run().statistics

    assert statistics.total_attempts == 4
    assert statistics.successful_attempts == 2
    assert statistics.failed_attempts == 2


def test_statistics_count_retries() -> None:
    statistics = create_run().statistics

    assert statistics.retry_count == 2


def test_statistics_compute_duration() -> None:
    statistics = create_run().statistics

    assert statistics.duration_seconds == 5.0


def test_statistics_are_deterministic() -> None:
    run = create_run()

    assert run.statistics == run.statistics


def test_statistics_count_failed_steps() -> None:
    failed_step = WorkflowStepRun(
        step_id=STEP_ONE_ID,
        layer_index=0,
        status=WorkflowStepStatus.FAILED,
        execution=None,
        attempts=(
            create_failed_attempt(
                attempt_number=1,
            ),
            create_failed_attempt(
                attempt_number=2,
            ),
        ),
        values=(),
    )

    run = WorkflowRun(
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Failed statistics workflow",
            description="Count failed workflow steps.",
            version="1.0.0",
        ),
        steps=(failed_step,),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    statistics = run.statistics

    assert statistics.total_steps == 1
    assert statistics.executed_steps == 0
    assert statistics.failed_steps == 1
    assert statistics.skipped_steps == 0

    assert statistics.total_attempts == 2
    assert statistics.successful_attempts == 0
    assert statistics.failed_attempts == 2
    assert statistics.retry_count == 1

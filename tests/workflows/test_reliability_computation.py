"""Tests for computing workflow reliability metrics."""

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

WORKFLOW_ID = UUID("41d92218-c536-44f8-a647-a30448d48eb5")

STEP_ONE_ID = UUID("8f152b56-b7f3-4ae7-9809-a9c97dfaeec6")
STEP_TWO_ID = UUID("16822e54-f050-4492-b5bd-c4fd8a998814")
STEP_THREE_ID = UUID("d42f0f61-28b0-4533-972c-e11262f710cf")
STEP_FOUR_ID = UUID("ba4cabbd-4683-4426-8bb1-f07254352f68")

STRATEGY_ONE_ID = UUID("ee9d0126-0815-4099-be44-c587ad57ce28")
STRATEGY_TWO_ID = UUID("a0dc2ccb-dd61-4e17-aed4-c272783a8635")

STARTED_AT = datetime(
    2026,
    8,
    11,
    14,
    0,
    tzinfo=UTC,
)

COMPLETED_AT = datetime(
    2026,
    8,
    11,
    14,
    0,
    5,
    tzinfo=UTC,
)


def create_execution(
    *,
    strategy_id: UUID,
    name: str,
) -> ExecutionResult:
    """Create a deterministic execution result."""

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
    """Create a successful workflow step attempt."""

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
    """Create a failed workflow step attempt."""

    return WorkflowStepAttempt(
        attempt_number=attempt_number,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        failure=WorkflowStepFailure(
            exception_type="RuntimeError",
            message="failure",
        ),
    )


def create_run() -> WorkflowRun:
    """Create a workflow run with mixed reliability outcomes."""

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
            name="Reliability workflow",
            description="Compute workflow reliability.",
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
                    create_successful_attempt(
                        attempt_number=2,
                        execution=second_execution,
                    ),
                ),
            ),
            WorkflowStepRun(
                step_id=STEP_THREE_ID,
                layer_index=1,
                status=WorkflowStepStatus.FAILED,
                execution=None,
                attempts=(
                    create_failed_attempt(
                        attempt_number=1,
                    ),
                ),
                values=(),
            ),
            WorkflowStepRun(
                step_id=STEP_FOUR_ID,
                layer_index=2,
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


def test_reliability_computes_completion_rate() -> None:
    metrics = create_run().reliability

    assert metrics.completion_rate == 0.5


def test_reliability_computes_first_attempt_success_rate() -> None:
    metrics = create_run().reliability

    assert metrics.first_attempt_success_rate == 1 / 3


def test_reliability_computes_retry_rate() -> None:
    metrics = create_run().reliability

    assert metrics.retry_rate == 1 / 3


def test_reliability_computes_failure_rate() -> None:
    metrics = create_run().reliability

    assert metrics.failure_rate == 1 / 3


def test_skipped_steps_do_not_count_as_attempted() -> None:
    run = create_run()

    attempted_steps = run.statistics.executed_steps + run.statistics.failed_steps

    assert attempted_steps == 3

    assert run.reliability.failure_rate == 1 / 3


def test_retry_rate_counts_retried_steps_not_retry_attempts() -> None:
    run = create_run()

    assert run.retry_count == 1
    assert run.reliability.retry_rate == 1 / 3


def test_reliability_is_deterministic() -> None:
    run = create_run()

    assert run.reliability == run.reliability

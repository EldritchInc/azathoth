"""Tests for recorded workflow step execution attempts."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows import (
    WorkflowStepAttempt,
    WorkflowStepFailure,
)

STRATEGY_ID = UUID("74350d20-3149-4754-b8ba-0ece85366ed2")

STARTED_AT = datetime(
    2026,
    8,
    10,
    22,
    0,
    tzinfo=UTC,
)

COMPLETED_AT = datetime(
    2026,
    8,
    10,
    22,
    0,
    1,
    tzinfo=UTC,
)


def create_execution_result() -> ExecutionResult:
    """Create a deterministic successful execution result."""

    context = Context()

    return ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="Attempt strategy",
        strategy_version="1.0.0",
        output="success",
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def create_failure() -> WorkflowStepFailure:
    """Create a deterministic workflow step failure."""

    return WorkflowStepFailure(
        exception_type="RuntimeError",
        message="temporary provider failure",
    )


def test_workflow_step_failure_records_exception_details() -> None:
    failure = create_failure()

    assert failure.exception_type == "RuntimeError"
    assert failure.message == "temporary provider failure"


def test_workflow_step_failure_is_immutable() -> None:
    failure = create_failure()

    with pytest.raises(ValidationError):
        failure.message = "different failure"


def test_successful_attempt_records_execution_result() -> None:
    execution = create_execution_result()

    attempt = WorkflowStepAttempt(
        attempt_number=1,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        execution=execution,
    )

    assert attempt.attempt_number == 1
    assert attempt.execution == execution
    assert attempt.failure is None
    assert attempt.succeeded


def test_failed_attempt_records_failure() -> None:
    failure = create_failure()

    attempt = WorkflowStepAttempt(
        attempt_number=2,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        failure=failure,
    )

    assert attempt.attempt_number == 2
    assert attempt.execution is None
    assert attempt.failure == failure
    assert not attempt.succeeded


def test_attempt_number_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        WorkflowStepAttempt(
            attempt_number=0,
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
            failure=create_failure(),
        )


def test_attempt_requires_an_outcome() -> None:
    with pytest.raises(
        ValidationError,
        match="exactly one",
    ):
        WorkflowStepAttempt(
            attempt_number=1,
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
        )


def test_attempt_rejects_both_execution_and_failure() -> None:
    with pytest.raises(
        ValidationError,
        match="exactly one",
    ):
        WorkflowStepAttempt(
            attempt_number=1,
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
            execution=create_execution_result(),
            failure=create_failure(),
        )


def test_attempt_rejects_completion_before_start() -> None:
    with pytest.raises(
        ValidationError,
        match="cannot precede",
    ):
        WorkflowStepAttempt(
            attempt_number=1,
            started_at=COMPLETED_AT,
            completed_at=STARTED_AT,
            failure=create_failure(),
        )


def test_successful_attempt_is_immutable() -> None:
    attempt = WorkflowStepAttempt(
        attempt_number=1,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        execution=create_execution_result(),
    )

    with pytest.raises(ValidationError):
        attempt.attempt_number = 2


def test_successful_attempt_round_trips_through_json() -> None:
    attempt = WorkflowStepAttempt(
        attempt_number=1,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        execution=create_execution_result(),
    )

    restored = WorkflowStepAttempt.model_validate_json(attempt.model_dump_json())

    assert restored == attempt
    assert restored.succeeded


def test_failed_attempt_round_trips_through_json() -> None:
    attempt = WorkflowStepAttempt(
        attempt_number=2,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        failure=create_failure(),
    )

    restored = WorkflowStepAttempt.model_validate_json(attempt.model_dump_json())

    assert restored == attempt
    assert not restored.succeeded

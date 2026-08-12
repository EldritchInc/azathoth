"""Tests for workflow evaluation."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    WorkflowEvaluation,
    WorkflowReliabilityMetrics,
    WorkflowRunStatistics,
)

WORKFLOW_ID = UUID("84f66d56-3d55-4a2b-a7ef-2a0b73abcc5b")

EVALUATED_AT = datetime(
    2026,
    8,
    12,
    19,
    30,
    tzinfo=UTC,
)


def create_statistics() -> WorkflowRunStatistics:
    """Create deterministic workflow statistics."""

    return WorkflowRunStatistics(
        total_steps=4,
        executed_steps=3,
        failed_steps=1,
        skipped_steps=0,
        total_attempts=5,
        successful_attempts=3,
        failed_attempts=2,
        retry_count=1,
        duration_seconds=2.5,
    )


def create_reliability() -> WorkflowReliabilityMetrics:
    """Create deterministic workflow reliability."""

    return WorkflowReliabilityMetrics(
        completion_rate=0.75,
        first_attempt_success_rate=2 / 3,
        retry_rate=1 / 3,
        failure_rate=1 / 3,
    )


def create_evaluation() -> WorkflowEvaluation:
    """Create a deterministic workflow evaluation."""

    return WorkflowEvaluation(
        workflow_id=WORKFLOW_ID,
        statistics=create_statistics(),
        reliability=create_reliability(),
        evaluated_at=EVALUATED_AT,
    )


def test_evaluation_records_workflow_id() -> None:
    evaluation = create_evaluation()

    assert evaluation.workflow_id == WORKFLOW_ID


def test_evaluation_records_statistics() -> None:
    evaluation = create_evaluation()

    assert evaluation.statistics == create_statistics()


def test_evaluation_records_reliability() -> None:
    evaluation = create_evaluation()

    assert evaluation.reliability == create_reliability()


def test_evaluation_records_timestamp() -> None:
    evaluation = create_evaluation()

    assert evaluation.evaluated_at == EVALUATED_AT


def test_evaluation_is_immutable() -> None:
    evaluation = create_evaluation()

    with pytest.raises(ValidationError):
        evaluation.workflow_id = UUID("00000000-0000-0000-0000-000000000000")


def test_evaluation_round_trips_through_json() -> None:
    evaluation = create_evaluation()

    restored = WorkflowEvaluation.model_validate_json(evaluation.model_dump_json())

    assert restored == evaluation

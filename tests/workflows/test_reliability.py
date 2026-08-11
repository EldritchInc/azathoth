"""Tests for workflow reliability metrics."""

import pytest
from pydantic import ValidationError

from azathoth.workflows import WorkflowReliabilityMetrics


def create_metrics() -> WorkflowReliabilityMetrics:
    """Create deterministic workflow reliability metrics."""

    return WorkflowReliabilityMetrics(
        completion_rate=0.75,
        first_attempt_success_rate=0.50,
        retry_rate=0.25,
        failure_rate=0.25,
    )


def test_reliability_metrics_record_values() -> None:
    metrics = create_metrics()

    assert metrics.completion_rate == 0.75
    assert metrics.first_attempt_success_rate == 0.50
    assert metrics.retry_rate == 0.25
    assert metrics.failure_rate == 0.25


@pytest.mark.parametrize(
    "field_name",
    (
        "completion_rate",
        "first_attempt_success_rate",
        "retry_rate",
        "failure_rate",
    ),
)
def test_reliability_metrics_reject_values_below_zero(
    field_name: str,
) -> None:
    values = {
        "completion_rate": 0.5,
        "first_attempt_success_rate": 0.5,
        "retry_rate": 0.5,
        "failure_rate": 0.5,
    }

    values[field_name] = -0.01

    with pytest.raises(ValidationError):
        WorkflowReliabilityMetrics(**values)


@pytest.mark.parametrize(
    "field_name",
    (
        "completion_rate",
        "first_attempt_success_rate",
        "retry_rate",
        "failure_rate",
    ),
)
def test_reliability_metrics_reject_values_above_one(
    field_name: str,
) -> None:
    values = {
        "completion_rate": 0.5,
        "first_attempt_success_rate": 0.5,
        "retry_rate": 0.5,
        "failure_rate": 0.5,
    }

    values[field_name] = 1.01

    with pytest.raises(ValidationError):
        WorkflowReliabilityMetrics(**values)


def test_reliability_metrics_accept_boundary_values() -> None:
    metrics = WorkflowReliabilityMetrics(
        completion_rate=1.0,
        first_attempt_success_rate=1.0,
        retry_rate=0.0,
        failure_rate=0.0,
    )

    assert metrics.completion_rate == 1.0
    assert metrics.first_attempt_success_rate == 1.0
    assert metrics.retry_rate == 0.0
    assert metrics.failure_rate == 0.0


def test_reliability_metrics_are_immutable() -> None:
    metrics = create_metrics()

    with pytest.raises(ValidationError):
        metrics.completion_rate = 1.0


def test_reliability_metrics_round_trip_through_json() -> None:
    metrics = create_metrics()

    restored = WorkflowReliabilityMetrics.model_validate_json(metrics.model_dump_json())

    assert restored == metrics

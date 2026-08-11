"""Tests for workflow execution statistics."""

import pytest
from pydantic import ValidationError

from azathoth.workflows import WorkflowRunStatistics


def create_statistics() -> WorkflowRunStatistics:
    """Create deterministic workflow execution statistics."""

    return WorkflowRunStatistics(
        total_steps=4,
        executed_steps=2,
        failed_steps=1,
        skipped_steps=1,
        total_attempts=5,
        successful_attempts=2,
        failed_attempts=3,
        retry_count=2,
        duration_seconds=1.5,
    )


def test_statistics_record_step_counts() -> None:
    statistics = create_statistics()

    assert statistics.total_steps == 4
    assert statistics.executed_steps == 2
    assert statistics.failed_steps == 1
    assert statistics.skipped_steps == 1


def test_statistics_record_attempt_counts() -> None:
    statistics = create_statistics()

    assert statistics.total_attempts == 5
    assert statistics.successful_attempts == 2
    assert statistics.failed_attempts == 3
    assert statistics.retry_count == 2


def test_statistics_record_duration() -> None:
    statistics = create_statistics()

    assert statistics.duration_seconds == 1.5


def test_statistics_reject_step_count_mismatch() -> None:
    with pytest.raises(
        ValidationError,
        match="sum to total_steps",
    ):
        WorkflowRunStatistics(
            total_steps=4,
            executed_steps=2,
            failed_steps=1,
            skipped_steps=0,
            total_attempts=0,
            successful_attempts=0,
            failed_attempts=0,
            retry_count=0,
            duration_seconds=0.0,
        )


def test_statistics_reject_attempt_count_mismatch() -> None:
    with pytest.raises(
        ValidationError,
        match="sum to total_attempts",
    ):
        WorkflowRunStatistics(
            total_steps=1,
            executed_steps=1,
            failed_steps=0,
            skipped_steps=0,
            total_attempts=3,
            successful_attempts=1,
            failed_attempts=1,
            retry_count=1,
            duration_seconds=0.0,
        )


def test_statistics_reject_retry_count_above_total_attempts() -> None:
    with pytest.raises(
        ValidationError,
        match="cannot exceed total attempts",
    ):
        WorkflowRunStatistics(
            total_steps=1,
            executed_steps=1,
            failed_steps=0,
            skipped_steps=0,
            total_attempts=1,
            successful_attempts=1,
            failed_attempts=0,
            retry_count=2,
            duration_seconds=0.0,
        )


def test_statistics_reject_negative_counts() -> None:
    with pytest.raises(ValidationError):
        WorkflowRunStatistics(
            total_steps=-1,
            executed_steps=0,
            failed_steps=0,
            skipped_steps=0,
            total_attempts=0,
            successful_attempts=0,
            failed_attempts=0,
            retry_count=0,
            duration_seconds=0.0,
        )


def test_statistics_reject_negative_duration() -> None:
    with pytest.raises(ValidationError):
        WorkflowRunStatistics(
            total_steps=0,
            executed_steps=0,
            failed_steps=0,
            skipped_steps=0,
            total_attempts=0,
            successful_attempts=0,
            failed_attempts=0,
            retry_count=0,
            duration_seconds=-0.1,
        )


def test_statistics_are_immutable() -> None:
    statistics = create_statistics()

    with pytest.raises(ValidationError):
        statistics.total_steps = 5


def test_statistics_round_trip_through_json() -> None:
    statistics = create_statistics()

    restored = WorkflowRunStatistics.model_validate_json(statistics.model_dump_json())

    assert restored == statistics

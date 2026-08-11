"""Tests for workflow retry policies."""

import pytest
from pydantic import ValidationError

from azathoth.workflows import WorkflowRetryPolicy


def test_retry_policy_defaults_to_single_attempt() -> None:
    policy = WorkflowRetryPolicy()

    assert policy.max_attempts == 1
    assert policy.initial_delay_seconds == 0.0
    assert policy.backoff_multiplier == 1.0
    assert policy.maximum_delay_seconds is None


def test_retry_policy_records_configured_values() -> None:
    policy = WorkflowRetryPolicy(
        max_attempts=4,
        initial_delay_seconds=0.5,
        backoff_multiplier=2.0,
        maximum_delay_seconds=5.0,
    )

    assert policy.max_attempts == 4
    assert policy.initial_delay_seconds == 0.5
    assert policy.backoff_multiplier == 2.0
    assert policy.maximum_delay_seconds == 5.0


def test_retry_policy_rejects_zero_attempts() -> None:
    with pytest.raises(ValidationError):
        WorkflowRetryPolicy(
            max_attempts=0,
        )


def test_retry_policy_rejects_negative_initial_delay() -> None:
    with pytest.raises(ValidationError):
        WorkflowRetryPolicy(
            initial_delay_seconds=-0.1,
        )


def test_retry_policy_rejects_backoff_multiplier_below_one() -> None:
    with pytest.raises(ValidationError):
        WorkflowRetryPolicy(
            backoff_multiplier=0.5,
        )


def test_retry_policy_rejects_negative_maximum_delay() -> None:
    with pytest.raises(ValidationError):
        WorkflowRetryPolicy(
            maximum_delay_seconds=-1.0,
        )


def test_retry_policy_rejects_maximum_delay_below_initial_delay() -> None:
    with pytest.raises(
        ValidationError,
        match="maximum delay cannot be less than the initial delay",
    ):
        WorkflowRetryPolicy(
            initial_delay_seconds=2.0,
            maximum_delay_seconds=1.0,
        )


def test_retry_policy_allows_maximum_delay_equal_to_initial_delay() -> None:
    policy = WorkflowRetryPolicy(
        initial_delay_seconds=2.0,
        maximum_delay_seconds=2.0,
    )

    assert policy.maximum_delay_seconds == 2.0


def test_retry_policy_is_immutable() -> None:
    policy = WorkflowRetryPolicy(
        max_attempts=3,
    )

    with pytest.raises(ValidationError):
        policy.max_attempts = 4


def test_retry_policy_round_trips_through_json() -> None:
    policy = WorkflowRetryPolicy(
        max_attempts=5,
        initial_delay_seconds=0.25,
        backoff_multiplier=2.0,
        maximum_delay_seconds=4.0,
    )

    restored = WorkflowRetryPolicy.model_validate_json(policy.model_dump_json())

    assert restored == policy

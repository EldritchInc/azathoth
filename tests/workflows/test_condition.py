"""Tests for workflow conditions."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    WorkflowCondition,
    WorkflowValueReference,
)

STEP_ID = UUID("4bd01bff-0db4-47be-babb-0b20f9d20a9d")


def create_condition() -> WorkflowCondition:
    """Create a deterministic workflow condition."""

    return WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
        expected="math",
    )


def test_workflow_condition_records_source_and_expected_value() -> None:
    condition = create_condition()

    assert condition.source == WorkflowValueReference(
        producer_step_id=STEP_ID,
        name="classification",
    )
    assert condition.expected == "math"


def test_workflow_condition_supports_structured_json_values() -> None:
    condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
        expected={
            "category": "math",
            "confidence": 0.98,
            "labels": [
                "reasoning",
                "calculation",
            ],
        },
    )

    assert condition.expected == {
        "category": "math",
        "confidence": 0.98,
        "labels": [
            "reasoning",
            "calculation",
        ],
    }


def test_workflow_condition_supports_boolean_values() -> None:
    condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="approved",
        ),
        expected=True,
    )

    assert condition.expected is True


def test_workflow_condition_supports_numeric_values() -> None:
    condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="confidence",
        ),
        expected=0.95,
    )

    assert condition.expected == 0.95


def test_workflow_condition_supports_null_value() -> None:
    condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="optional_result",
        ),
        expected=None,
    )

    assert condition.expected is None


def test_workflow_condition_is_immutable() -> None:
    condition = create_condition()

    with pytest.raises(ValidationError):
        condition.expected = "general"


def test_workflow_condition_round_trips_through_json() -> None:
    condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
        expected={
            "category": "math",
            "confidence": 0.98,
        },
    )

    restored = WorkflowCondition.model_validate_json(condition.model_dump_json())

    assert restored == condition


def test_equivalent_workflow_conditions_are_equal() -> None:
    first = create_condition()
    second = create_condition()

    assert first == second


def test_workflow_conditions_with_different_sources_are_not_equal() -> None:
    other_step_id = UUID("c7616e66-0a44-4d41-873c-d17df519f2ec")

    first = create_condition()
    second = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=other_step_id,
            name="classification",
        ),
        expected="math",
    )

    assert first != second


def test_workflow_conditions_with_different_expected_values_are_not_equal() -> None:
    first = create_condition()
    second = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
        expected="general",
    )

    assert first != second

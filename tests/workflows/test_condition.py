"""Tests for workflow conditions."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    WorkflowCondition,
    WorkflowConditionOperator,
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


def test_workflow_condition_defaults_to_equality() -> None:
    condition = create_condition()

    assert condition.operator is WorkflowConditionOperator.EQUAL


def test_workflow_condition_records_explicit_operator() -> None:
    condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
        operator=WorkflowConditionOperator.NOT_EQUAL,
        expected="general",
    )

    assert condition.operator is WorkflowConditionOperator.NOT_EQUAL
    assert condition.expected == "general"


@pytest.mark.parametrize(
    "operator",
    (
        WorkflowConditionOperator.EQUAL,
        WorkflowConditionOperator.NOT_EQUAL,
        WorkflowConditionOperator.GREATER_THAN,
        WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
        WorkflowConditionOperator.LESS_THAN,
        WorkflowConditionOperator.LESS_THAN_OR_EQUAL,
    ),
)
def test_workflow_condition_supports_comparison_operators(
    operator: WorkflowConditionOperator,
) -> None:
    condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="confidence",
        ),
        operator=operator,
        expected=0.95,
    )

    assert condition.operator is operator


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


def test_workflow_condition_operator_is_immutable() -> None:
    condition = create_condition()

    with pytest.raises(ValidationError):
        condition.operator = WorkflowConditionOperator.NOT_EQUAL


def test_workflow_condition_round_trips_through_json() -> None:
    condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
        operator=WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
        expected={
            "category": "math",
            "confidence": 0.98,
        },
    )

    restored = WorkflowCondition.model_validate_json(condition.model_dump_json())

    assert restored == condition
    assert restored.operator is WorkflowConditionOperator.GREATER_THAN_OR_EQUAL


def test_workflow_condition_serialization_records_operator() -> None:
    condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="latency_ms",
        ),
        operator=WorkflowConditionOperator.LESS_THAN,
        expected=500,
    )

    serialized = condition.model_dump()

    assert serialized["operator"] == WorkflowConditionOperator.LESS_THAN


def test_existing_equality_condition_shape_remains_valid() -> None:
    condition = WorkflowCondition.model_validate(
        {
            "source": {
                "producer_step_id": str(STEP_ID),
                "name": "classification",
            },
            "expected": "math",
        }
    )

    assert condition.operator is WorkflowConditionOperator.EQUAL
    assert condition.expected == "math"


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


def test_workflow_conditions_with_different_operators_are_not_equal() -> None:
    first = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="confidence",
        ),
        operator=WorkflowConditionOperator.GREATER_THAN,
        expected=0.9,
    )
    second = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="confidence",
        ),
        operator=WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
        expected=0.9,
    )

    assert first != second

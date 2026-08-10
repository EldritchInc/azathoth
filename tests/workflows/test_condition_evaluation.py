"""Tests for evaluating workflow condition operators."""

from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.workflows import (
    WorkflowCondition,
    WorkflowConditionEvaluationError,
    WorkflowConditionOperator,
    WorkflowValueReference,
)

STEP_ID = UUID("ca6823e1-c44a-40ef-aa99-c0fc19fc1b71")


def create_condition(
    *,
    operator: WorkflowConditionOperator,
    expected: JsonValue,
) -> WorkflowCondition:
    """Create a deterministic workflow condition."""

    return WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="value",
        ),
        operator=operator,
        expected=expected,
    )


def test_equal_matches_equal_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.EQUAL,
        expected="math",
    )

    assert condition.matches("math")


def test_equal_rejects_different_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.EQUAL,
        expected="math",
    )

    assert not condition.matches("general")


def test_not_equal_matches_different_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.NOT_EQUAL,
        expected="math",
    )

    assert condition.matches("general")


def test_not_equal_rejects_equal_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.NOT_EQUAL,
        expected="math",
    )

    assert not condition.matches("math")


def test_greater_than_compares_numeric_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.GREATER_THAN,
        expected=0.9,
    )

    assert condition.matches(0.95)
    assert not condition.matches(0.9)
    assert not condition.matches(0.85)


def test_greater_than_or_equal_compares_numeric_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
        expected=0.9,
    )

    assert condition.matches(0.95)
    assert condition.matches(0.9)
    assert not condition.matches(0.85)


def test_less_than_compares_numeric_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.LESS_THAN,
        expected=500,
    )

    assert condition.matches(499)
    assert not condition.matches(500)
    assert not condition.matches(501)


def test_less_than_or_equal_compares_numeric_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.LESS_THAN_OR_EQUAL,
        expected=500,
    )

    assert condition.matches(499)
    assert condition.matches(500)
    assert not condition.matches(501)


def test_ordering_comparison_supports_int_and_float() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.GREATER_THAN,
        expected=10,
    )

    assert condition.matches(10.5)


def test_equality_supports_structured_json_values() -> None:
    expected: JsonValue = {
        "category": "math",
        "confidence": 0.98,
    }

    condition = create_condition(
        operator=WorkflowConditionOperator.EQUAL,
        expected=expected,
    )

    assert condition.matches(
        {
            "category": "math",
            "confidence": 0.98,
        }
    )


def test_inequality_supports_structured_json_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.NOT_EQUAL,
        expected={
            "category": "math",
        },
    )

    assert condition.matches(
        {
            "category": "general",
        }
    )


@pytest.mark.parametrize(
    "operator",
    (
        WorkflowConditionOperator.GREATER_THAN,
        WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
        WorkflowConditionOperator.LESS_THAN,
        WorkflowConditionOperator.LESS_THAN_OR_EQUAL,
    ),
)
def test_ordering_comparison_rejects_non_numeric_actual_value(
    operator: WorkflowConditionOperator,
) -> None:
    condition = create_condition(
        operator=operator,
        expected=0.9,
    )

    with pytest.raises(
        WorkflowConditionEvaluationError,
        match="actual",
    ):
        condition.matches("high")


@pytest.mark.parametrize(
    "operator",
    (
        WorkflowConditionOperator.GREATER_THAN,
        WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
        WorkflowConditionOperator.LESS_THAN,
        WorkflowConditionOperator.LESS_THAN_OR_EQUAL,
    ),
)
def test_ordering_comparison_rejects_non_numeric_expected_value(
    operator: WorkflowConditionOperator,
) -> None:
    condition = create_condition(
        operator=operator,
        expected="high",
    )

    with pytest.raises(
        WorkflowConditionEvaluationError,
        match="expected",
    ):
        condition.matches(0.95)


@pytest.mark.parametrize(
    "operator",
    (
        WorkflowConditionOperator.GREATER_THAN,
        WorkflowConditionOperator.GREATER_THAN_OR_EQUAL,
        WorkflowConditionOperator.LESS_THAN,
        WorkflowConditionOperator.LESS_THAN_OR_EQUAL,
    ),
)
def test_ordering_comparison_does_not_treat_bool_as_number(
    operator: WorkflowConditionOperator,
) -> None:
    condition = create_condition(
        operator=operator,
        expected=1,
    )

    with pytest.raises(
        WorkflowConditionEvaluationError,
        match="actual",
    ):
        condition.matches(True)


def test_equality_can_compare_boolean_values() -> None:
    condition = create_condition(
        operator=WorkflowConditionOperator.EQUAL,
        expected=True,
    )

    assert condition.matches(True)
    assert not condition.matches(False)

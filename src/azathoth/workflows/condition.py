"""Conditional workflow execution."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, JsonValue

from azathoth.workflows.value import WorkflowValueReference


class WorkflowConditionOperator(StrEnum):
    """Comparison operators supported by workflow conditions."""

    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


class WorkflowCondition(BaseModel):
    """Require a workflow value to satisfy a comparison."""

    model_config = ConfigDict(frozen=True)

    source: WorkflowValueReference
    operator: WorkflowConditionOperator = WorkflowConditionOperator.EQUAL
    expected: JsonValue

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


class WorkflowConditionEvaluationError(ValueError):
    """Raised when a workflow condition cannot compare its operands."""


class WorkflowCondition(BaseModel):
    """Require a workflow value to satisfy a comparison."""

    model_config = ConfigDict(frozen=True)

    source: WorkflowValueReference
    operator: WorkflowConditionOperator = WorkflowConditionOperator.EQUAL
    expected: JsonValue

    def matches(
        self,
        actual: JsonValue,
    ) -> bool:
        """Return whether an actual workflow value satisfies this condition."""

        if self.operator is WorkflowConditionOperator.EQUAL:
            return actual == self.expected

        if self.operator is WorkflowConditionOperator.NOT_EQUAL:
            return actual != self.expected

        actual_number = self._numeric_operand(
            actual,
            operand_name="actual",
        )
        expected_number = self._numeric_operand(
            self.expected,
            operand_name="expected",
        )

        if self.operator is WorkflowConditionOperator.GREATER_THAN:
            return actual_number > expected_number

        if self.operator is WorkflowConditionOperator.GREATER_THAN_OR_EQUAL:
            return actual_number >= expected_number

        if self.operator is WorkflowConditionOperator.LESS_THAN:
            return actual_number < expected_number

        if self.operator is WorkflowConditionOperator.LESS_THAN_OR_EQUAL:
            return actual_number <= expected_number

        raise AssertionError(f"Unsupported workflow condition operator: {self.operator!r}")

    @staticmethod
    def _numeric_operand(
        value: JsonValue,
        *,
        operand_name: str,
    ) -> int | float:
        """Return a numeric comparison operand."""

        if isinstance(value, bool) or not isinstance(
            value,
            (int, float),
        ):
            raise WorkflowConditionEvaluationError(
                "Workflow ordering conditions require numeric operands; "
                f"{operand_name} value was {value!r}."
            )

        return value

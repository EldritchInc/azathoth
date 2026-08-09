"""Conditional workflow execution."""

# from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    # Field,
    JsonValue,
)

from azathoth.workflows.value import WorkflowValueReference


class WorkflowCondition(BaseModel):
    """Require a workflow value to equal an expected value."""

    model_config = ConfigDict(frozen=True)

    source: WorkflowValueReference
    expected: JsonValue

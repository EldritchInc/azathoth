"""Structured values produced by workflow execution."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class WorkflowValue(BaseModel):
    """A structured value produced by a workflow step."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    value: JsonValue
    producer_step_id: UUID


class WorkflowValueBinding(BaseModel):
    """Declare a named value exported from a workflow step output."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    path: tuple[str | int, ...] = ()

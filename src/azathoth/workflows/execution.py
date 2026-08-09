"""Recorded results of executable workflow runs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows.models import WorkflowMetadata
from azathoth.workflows.value import WorkflowValue


class WorkflowStepRun(BaseModel):
    """The recorded execution of one workflow step."""

    model_config = ConfigDict(frozen=True)

    step_id: UUID
    layer_index: int = Field(ge=0)
    execution: ExecutionResult
    values: tuple[WorkflowValue, ...] = ()


class WorkflowRun(BaseModel):
    """The complete recorded result of executing one workflow candidate."""

    model_config = ConfigDict(frozen=True)

    workflow: WorkflowMetadata
    steps: tuple[WorkflowStepRun, ...] = Field(min_length=1)

    initial_context: Context
    final_context: Context

    started_at: datetime
    completed_at: datetime

    @model_validator(mode="after")
    def validate_timestamps(self) -> "WorkflowRun":
        """Ensure workflow completion does not precede workflow start."""

        if self.completed_at < self.started_at:
            raise ValueError("Workflow completion time cannot precede its start time.")

        return self

    @property
    def values(self) -> tuple[WorkflowValue, ...]:
        """Return all workflow values in recorded execution order."""

        return tuple(value for step in self.steps for value in step.values)

    def values_named(
        self,
        name: str,
    ) -> tuple[WorkflowValue, ...]:
        """Return all workflow values with the supplied name."""

        return tuple(value for value in self.values if value.name == name)

    def values_from(
        self,
        producer_step_id: UUID,
    ) -> tuple[WorkflowValue, ...]:
        """Return all values produced by one workflow step."""

        return tuple(value for value in self.values if value.producer_step_id == producer_step_id)

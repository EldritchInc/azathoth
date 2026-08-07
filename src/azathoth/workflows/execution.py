"""Recorded results of executable workflow runs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows.models import WorkflowMetadata


class WorkflowStepRun(BaseModel):
    """The recorded execution of one workflow step."""

    model_config = ConfigDict(frozen=True)

    step_id: UUID
    layer_index: int = Field(ge=0)
    execution: ExecutionResult


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

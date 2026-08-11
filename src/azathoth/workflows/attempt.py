"""Recorded workflow step execution attempts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.execution import ExecutionResult


class WorkflowStepFailure(BaseModel):
    """Durable information describing a failed workflow step attempt."""

    model_config = ConfigDict(frozen=True)

    exception_type: str = Field(min_length=1)
    message: str


class WorkflowStepAttempt(BaseModel):
    """Record one attempt to execute a workflow step."""

    model_config = ConfigDict(frozen=True)

    attempt_number: int = Field(ge=1)

    started_at: datetime
    completed_at: datetime

    execution: ExecutionResult | None = None
    failure: WorkflowStepFailure | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "WorkflowStepAttempt":
        """Ensure an attempt records exactly one outcome."""

        has_execution = self.execution is not None
        has_failure = self.failure is not None

        if has_execution == has_failure:
            raise ValueError(
                "Workflow step attempts must contain exactly one execution result or failure."
            )

        return self

    @model_validator(mode="after")
    def validate_timestamps(self) -> "WorkflowStepAttempt":
        """Ensure attempt completion does not precede attempt start."""

        if self.completed_at < self.started_at:
            raise ValueError("Workflow step attempt completion time cannot precede its start time.")

        return self

    @property
    def succeeded(self) -> bool:
        """Return whether the workflow step attempt succeeded."""

        return self.execution is not None

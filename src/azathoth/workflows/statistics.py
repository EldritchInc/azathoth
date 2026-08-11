"""Workflow execution statistics models."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowRunStatistics(BaseModel):
    """Summarize durable workflow execution activity."""

    model_config = ConfigDict(frozen=True)

    total_steps: int = Field(ge=0)

    executed_steps: int = Field(ge=0)
    failed_steps: int = Field(ge=0)
    skipped_steps: int = Field(ge=0)

    total_attempts: int = Field(ge=0)
    successful_attempts: int = Field(ge=0)
    failed_attempts: int = Field(ge=0)

    retry_count: int = Field(ge=0)

    duration_seconds: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_step_counts(self) -> "WorkflowRunStatistics":
        """Ensure step counts reconcile with the workflow total."""

        if self.executed_steps + self.failed_steps + self.skipped_steps != self.total_steps:
            raise ValueError("Workflow step statistics must sum to total_steps.")

        return self

    @model_validator(mode="after")
    def validate_attempt_counts(self) -> "WorkflowRunStatistics":
        """Ensure attempt counts reconcile with the attempt total."""

        if self.successful_attempts + self.failed_attempts != self.total_attempts:
            raise ValueError("Workflow attempt statistics must sum to total_attempts.")

        return self

    @model_validator(mode="after")
    def validate_retry_count(self) -> "WorkflowRunStatistics":
        """Ensure retry count does not exceed recorded attempts."""

        if self.retry_count > self.total_attempts:
            raise ValueError("Workflow retry count cannot exceed total attempts.")

        return self

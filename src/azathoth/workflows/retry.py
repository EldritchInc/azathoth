"""Workflow retry policy models."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowRetryPolicy(BaseModel):
    """Configure retry behavior for a workflow step."""

    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=1, ge=1)
    initial_delay_seconds: float = Field(default=0.0, ge=0.0)
    backoff_multiplier: float = Field(default=1.0, ge=1.0)
    maximum_delay_seconds: float | None = Field(
        default=None,
        ge=0.0,
    )

    @model_validator(mode="after")
    def validate_maximum_delay(self) -> "WorkflowRetryPolicy":
        """Ensure the maximum delay is compatible with the initial delay."""

        if (
            self.maximum_delay_seconds is not None
            and self.maximum_delay_seconds < self.initial_delay_seconds
        ):
            raise ValueError("Workflow retry maximum delay cannot be less than the initial delay.")

        return self

"""Workflow reliability metric models."""

from pydantic import BaseModel, ConfigDict, Field


class WorkflowReliabilityMetrics(BaseModel):
    """Summarize normalized workflow execution reliability."""

    model_config = ConfigDict(frozen=True)

    completion_rate: float = Field(
        ge=0.0,
        le=1.0,
    )
    first_attempt_success_rate: float = Field(
        ge=0.0,
        le=1.0,
    )
    retry_rate: float = Field(
        ge=0.0,
        le=1.0,
    )
    failure_rate: float = Field(
        ge=0.0,
        le=1.0,
    )

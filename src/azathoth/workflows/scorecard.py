"""Workflow scorecard models."""

from pydantic import BaseModel, ConfigDict, Field


class WorkflowScorecard(BaseModel):
    """Represent scored workflow execution quality."""

    model_config = ConfigDict(frozen=True)

    quality_score: float = Field(
        ge=0.0,
        le=1.0,
    )
    reliability_score: float = Field(
        ge=0.0,
        le=1.0,
    )
    latency_score: float = Field(
        ge=0.0,
        le=1.0,
    )
    cost_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    overall_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    rationale: str = ""

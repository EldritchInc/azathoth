"""Workflow scorecard models."""

from typing import cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    model_serializer,
)


class WorkflowScorecard(BaseModel):
    """Represent scored workflow execution quality.

    `citation_score` is the fraction of citations a run's cited steps kept
    that verified, or None for a run with no cited step (ADR 0117). A
    scorecard without one serializes without it, so every scorecard recorded
    before it reads and writes as it did.
    """

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
    citation_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    overall_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    rationale: str = ""

    @model_serializer(mode="wrap")
    def omit_absent_citation_score(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """Leave out `citation_score` when the scorecard has none."""

        serialized = cast(dict[str, JsonValue], handler(self))

        if self.citation_score is None:
            serialized.pop("citation_score", None)

        return serialized

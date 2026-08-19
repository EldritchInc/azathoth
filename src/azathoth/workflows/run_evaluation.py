"""Evaluator judgments associated with durable workflow runs."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from azathoth.evaluation import EvaluationResult


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class WorkflowRunEvaluation(BaseModel):
    """Associate one evaluator judgment with one completed workflow run."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    evaluation: EvaluationResult
    evaluated_at: datetime = Field(default_factory=utc_now)

    @property
    def id(self) -> UUID:
        """Return the durable evaluation identifier."""

        return self.evaluation.id

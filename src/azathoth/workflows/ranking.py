"""Workflow ranking models."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.workflows.scorecard import WorkflowScorecard


class RankedWorkflow(BaseModel):
    """A workflow scorecard assigned a deterministic rank."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    scorecard: WorkflowScorecard


class WorkflowRanking(BaseModel):
    """An ordered comparison of workflow scorecards."""

    model_config = ConfigDict(frozen=True)

    entries: tuple[RankedWorkflow, ...] = Field(
        min_length=1,
    )

    @property
    def winner(self) -> WorkflowScorecard:
        """Return the highest-ranked workflow scorecard."""

        return self.entries[0].scorecard

    @model_validator(mode="after")
    def validate_rank_order(self) -> "WorkflowRanking":
        """Ensure ranking positions are consecutive and ordered."""

        expected_ranks = tuple(
            range(
                1,
                len(self.entries) + 1,
            )
        )

        actual_ranks = tuple(entry.rank for entry in self.entries)

        if actual_ranks != expected_ranks:
            raise ValueError("Workflow ranking entries must use consecutive ranks starting at 1.")

        return self

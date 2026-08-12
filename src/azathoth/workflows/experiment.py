"""Workflow experiment models."""

from pydantic import BaseModel, ConfigDict, Field

from azathoth.workflows.ranking import WorkflowRanking
from azathoth.workflows.scorecard import WorkflowScorecard


class WorkflowExperimentResult(BaseModel):
    """The durable result of comparing multiple workflow executions."""

    model_config = ConfigDict(frozen=True)

    scorecards: tuple[WorkflowScorecard, ...] = Field(
        min_length=1,
    )

    ranking: WorkflowRanking

    @property
    def winner(self) -> WorkflowScorecard:
        """Return the highest-ranked workflow scorecard."""

        return self.ranking.winner

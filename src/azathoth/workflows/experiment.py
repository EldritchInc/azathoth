"""Workflow experiment models."""

from pydantic import BaseModel, ConfigDict, Field

from azathoth.workflows.candidate import WorkflowCandidateSignature
from azathoth.workflows.ranking import WorkflowRanking
from azathoth.workflows.scorecard import WorkflowScorecard


class WorkflowExperimentEvidence(BaseModel):
    """Associate one resolved workflow candidate with its scorecard."""

    model_config = ConfigDict(frozen=True)

    candidate_signature: WorkflowCandidateSignature
    scorecard: WorkflowScorecard


class WorkflowExperimentResult(BaseModel):
    """The immutable result of comparing multiple workflow executions."""

    model_config = ConfigDict(frozen=True)

    evidence: tuple[WorkflowExperimentEvidence, ...] = Field(
        min_length=1,
    )

    ranking: WorkflowRanking

    @property
    def scorecards(
        self,
    ) -> tuple[WorkflowScorecard, ...]:
        """Return scorecards in candidate experiment order."""

        return tuple(observation.scorecard for observation in self.evidence)

    @property
    def winner(
        self,
    ) -> WorkflowScorecard:
        """Return the highest-ranked workflow scorecard."""

        return self.ranking.winner

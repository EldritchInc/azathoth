"""Workflow experiment models."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

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

    @model_validator(mode="after")
    def validate_ranking_evidence(
        self,
    ) -> "WorkflowExperimentResult":
        """Require ranking to contain exactly the observed scorecards."""

        remaining = list(self.evidence)

        for entry in self.ranking.entries:
            match_index = next(
                (
                    index
                    for index, observation in enumerate(remaining)
                    if observation.scorecard == entry.scorecard
                ),
                None,
            )

            if match_index is None:
                raise ValueError(
                    "Workflow experiment ranking must reference "
                    + "every evidence scorecard exactly once."
                )

            remaining.pop(match_index)

        if remaining:
            raise ValueError(
                "Workflow experiment ranking must reference every evidence scorecard exactly once."
            )

        return self

    @property
    def scorecards(
        self,
    ) -> tuple[WorkflowScorecard, ...]:
        """Return scorecards in candidate experiment order."""

        return tuple(observation.scorecard for observation in self.evidence)

    @property
    def ranked_evidence(
        self,
    ) -> tuple[WorkflowExperimentEvidence, ...]:
        """Return candidate evidence in deterministic ranking order."""

        remaining = list(self.evidence)
        ranked: list[WorkflowExperimentEvidence] = []

        for entry in self.ranking.entries:
            match_index = next(
                index
                for index, observation in enumerate(remaining)
                if observation.scorecard == entry.scorecard
            )

            ranked.append(remaining.pop(match_index))

        return tuple(ranked)

    @property
    def winner_evidence(
        self,
    ) -> WorkflowExperimentEvidence:
        """Return the evidence for the highest-ranked candidate."""

        return self.ranked_evidence[0]

    @property
    def winner(
        self,
    ) -> WorkflowScorecard:
        """Return the highest-ranked workflow scorecard."""

        return self.winner_evidence.scorecard

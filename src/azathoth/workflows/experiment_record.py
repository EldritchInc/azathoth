"""Durable records of completed workflow experiments."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.workflows.candidate import WorkflowCandidateSignature
from azathoth.workflows.models import WorkflowMetadata
from azathoth.workflows.scorecard import WorkflowScorecard


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class WorkflowExperimentObservation(BaseModel):
    """Record evidence identities and scoring for one workflow execution."""

    model_config = ConfigDict(frozen=True)

    workflow: WorkflowMetadata
    candidate_signature: WorkflowCandidateSignature
    run_id: UUID
    evaluation_id: UUID
    scorecard: WorkflowScorecard

    @model_validator(mode="after")
    def validate_candidate_workflow_identity(
        self,
    ) -> "WorkflowExperimentObservation":
        """Require candidate identity to reference the observed workflow."""

        if self.candidate_signature.workflow_id != self.workflow.id:
            raise ValueError(
                "Workflow experiment candidate signature must reference the observed workflow."
            )

        return self


class WorkflowExperimentRecord(BaseModel):
    """Record one durable comparison of workflow executions."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    observations: tuple[
        WorkflowExperimentObservation,
        ...,
    ] = Field(
        min_length=1,
    )

    ranking: tuple[UUID, ...] = Field(
        min_length=1,
    )

    recorded_at: datetime = Field(
        default_factory=utc_now,
    )

    @model_validator(mode="after")
    def validate_unique_run_ids(
        self,
    ) -> "WorkflowExperimentRecord":
        """Ensure every observation represents a distinct execution."""

        run_ids = tuple(observation.run_id for observation in self.observations)

        if len(run_ids) != len(set(run_ids)):
            raise ValueError("Workflow experiment observations must use unique run identifiers.")

        return self

    @model_validator(mode="after")
    def validate_unique_evaluation_ids(
        self,
    ) -> "WorkflowExperimentRecord":
        """Ensure every observation references a distinct evaluation."""

        evaluation_ids = tuple(observation.evaluation_id for observation in self.observations)

        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError(
                "Workflow experiment observations must use unique evaluation identifiers."
            )

        return self

    @model_validator(mode="after")
    def validate_ranking(
        self,
    ) -> "WorkflowExperimentRecord":
        """Ensure ranking references every observed run exactly once."""

        observation_run_ids = tuple(observation.run_id for observation in self.observations)

        if len(self.ranking) != len(set(self.ranking)):
            raise ValueError(
                "Workflow experiment ranking cannot contain duplicate run identifiers."
            )

        if set(self.ranking) != set(observation_run_ids):
            raise ValueError(
                "Workflow experiment ranking must reference every observed run exactly once."
            )

        return self

    @property
    def winner(
        self,
    ) -> WorkflowExperimentObservation:
        """Return the highest-ranked workflow observation."""

        winning_run_id = self.ranking[0]

        return next(
            observation for observation in self.observations if observation.run_id == winning_run_id
        )

    def observation_for_run(
        self,
        run_id: UUID,
    ) -> WorkflowExperimentObservation | None:
        """Return the observation for one workflow run."""

        return next(
            (observation for observation in self.observations if observation.run_id == run_id),
            None,
        )

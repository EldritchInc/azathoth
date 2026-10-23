"""Durable records of completed workflow experiments."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.revisions import CONTENT_DIGEST_PATTERN
from azathoth.workflows.candidate import WorkflowCandidateSignature
from azathoth.workflows.models import WorkflowMetadata
from azathoth.workflows.scorecard import WorkflowScorecard


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class WorkflowExperimentCaseObservation(BaseModel):
    """Record the evidence identities for one candidate execution of one case.

    The case identifier is absent for experiments that judged a single
    expected outcome rather than a benchmark case. Whether the case passed is
    absent for records written before per-case evidence existed.
    """

    model_config = ConfigDict(frozen=True)

    case_id: UUID | None = None
    run_id: UUID
    evaluation_id: UUID
    passed: bool | None = None


class WorkflowExperimentObservation(BaseModel):
    """Record evidence identities and combined scoring for one candidate.

    Records written before multi-case experiments held a single run and
    evaluation per observation. Those decode as one case without a case
    identifier, reusing the run identifier as the observation identifier so
    the legacy run-based ranking still resolves.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    workflow: WorkflowMetadata
    candidate_signature: WorkflowCandidateSignature

    cases: tuple[
        WorkflowExperimentCaseObservation,
        ...,
    ] = Field(
        min_length=1,
    )

    scorecard: WorkflowScorecard

    @model_validator(mode="before")
    @classmethod
    def convert_single_run_observation(
        cls,
        data: Any,
    ) -> Any:
        """Convert a legacy single-run observation into one unidentified case."""

        if not isinstance(data, dict) or "cases" in data or "run_id" not in data:
            return data

        converted = {
            key: value for key, value in data.items() if key not in {"run_id", "evaluation_id"}
        }

        converted.setdefault(
            "id",
            data["run_id"],
        )

        converted["cases"] = (
            {
                "case_id": None,
                "run_id": data["run_id"],
                "evaluation_id": data.get("evaluation_id"),
            },
        )

        return converted

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

    @model_validator(mode="after")
    def validate_unique_case_ids(
        self,
    ) -> "WorkflowExperimentObservation":
        """Ensure one observation judges each identified case at most once."""

        case_ids = tuple(case.case_id for case in self.cases if case.case_id is not None)

        if len(case_ids) != len(set(case_ids)):
            raise ValueError(
                "Workflow experiment observation cases must use unique case identifiers."
            )

        return self

    @property
    def cases_passed(self) -> int | None:
        """Return the number of passing cases, or None when any is unknown."""

        if any(case.passed is None for case in self.cases):
            return None

        return sum(case.passed is True for case in self.cases)

    def case_for_run(
        self,
        run_id: UUID,
    ) -> WorkflowExperimentCaseObservation | None:
        """Return the case observed through one workflow run."""

        return next(
            (case for case in self.cases if case.run_id == run_id),
            None,
        )


class WorkflowExperimentRecord(BaseModel):
    """Record one durable comparison of workflow candidates.

    The ranking lists observation identifiers, best first. Records written
    before benchmark-driven optimization have no benchmark identifier.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    benchmark_id: UUID | None = None

    benchmark_digest: str | None = Field(
        default=None,
        pattern=CONTENT_DIGEST_PATTERN,
    )

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
    def validate_unique_observation_ids(
        self,
    ) -> "WorkflowExperimentRecord":
        """Ensure every observation has a distinct identity."""

        observation_ids = tuple(observation.id for observation in self.observations)

        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError(
                "Workflow experiment observations must use unique observation identifiers."
            )

        return self

    @model_validator(mode="after")
    def validate_unique_run_ids(
        self,
    ) -> "WorkflowExperimentRecord":
        """Ensure every case across all observations represents a distinct execution."""

        run_ids = tuple(
            case.run_id for observation in self.observations for case in observation.cases
        )

        if len(run_ids) != len(set(run_ids)):
            raise ValueError("Workflow experiment observations must use unique run identifiers.")

        return self

    @model_validator(mode="after")
    def validate_unique_evaluation_ids(
        self,
    ) -> "WorkflowExperimentRecord":
        """Ensure every case across all observations references a distinct evaluation."""

        evaluation_ids = tuple(
            case.evaluation_id for observation in self.observations for case in observation.cases
        )

        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError(
                "Workflow experiment observations must use unique evaluation identifiers."
            )

        return self

    @model_validator(mode="after")
    def validate_ranking(
        self,
    ) -> "WorkflowExperimentRecord":
        """Ensure ranking references every observation exactly once."""

        observation_ids = tuple(observation.id for observation in self.observations)

        if len(self.ranking) != len(set(self.ranking)):
            raise ValueError(
                "Workflow experiment ranking cannot contain duplicate observation identifiers."
            )

        if set(self.ranking) != set(observation_ids):
            raise ValueError(
                "Workflow experiment ranking must reference every observation exactly once."
            )

        return self

    @property
    def winner(
        self,
    ) -> WorkflowExperimentObservation:
        """Return the highest-ranked workflow observation."""

        return self.ranked_observations[0]

    @property
    def ranked_observations(
        self,
    ) -> tuple[WorkflowExperimentObservation, ...]:
        """Return every observation in rank order, best first."""

        observations = {observation.id: observation for observation in self.observations}

        return tuple(observations[observation_id] for observation_id in self.ranking)

    def observation(
        self,
        observation_id: UUID,
    ) -> WorkflowExperimentObservation | None:
        """Return one observation by its identifier."""

        return next(
            (observation for observation in self.observations if observation.id == observation_id),
            None,
        )

    def observation_for_run(
        self,
        run_id: UUID,
    ) -> WorkflowExperimentObservation | None:
        """Return the observation whose cases include one workflow run."""

        return next(
            (
                observation
                for observation in self.observations
                if observation.case_for_run(run_id) is not None
            ),
            None,
        )

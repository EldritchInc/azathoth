"""Durable records of completed workflow benchmark executions."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.evaluation import OutcomeComparison
from azathoth.revisions import CONTENT_DIGEST_PATTERN
from azathoth.workflows.benchmark import WorkflowBenchmarkComparisonTally
from azathoth.workflows.candidate import WorkflowCandidateSignature
from azathoth.workflows.models import WorkflowMetadata
from azathoth.workflows.scorecard import WorkflowScorecard
from azathoth.workflows.scoring import WorkflowScoringPolicy


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class WorkflowBenchmarkExecutionKind(StrEnum):
    """The benchmark command that produced an execution record."""

    RUN = "run"
    COMPARE = "compare"


class WorkflowBenchmarkExecutionCase(BaseModel):
    """Record the evidence identities and outcome of one executed case.

    Judge calls and their cost belong to the evaluation, never to the run, so
    they are recorded here beside the run rather than inside it.
    """

    model_config = ConfigDict(frozen=True)

    case_id: UUID
    comparison: OutcomeComparison
    run_id: UUID
    evaluation_id: UUID
    passed: bool
    run_failure: bool = False

    judge_calls: int = Field(
        default=0,
        ge=0,
    )

    judge_cost_usd: float = Field(
        default=0.0,
        ge=0.0,
    )


class WorkflowBenchmarkExecutionCandidate(BaseModel):
    """Record one workflow candidate's evidence across every benchmark case.

    The scorecard is present only for comparisons, which score and rank
    candidates under a scoring policy.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    workflow: WorkflowMetadata
    candidate_signature: WorkflowCandidateSignature

    cases: tuple[
        WorkflowBenchmarkExecutionCase,
        ...,
    ] = Field(
        min_length=1,
    )

    scorecard: WorkflowScorecard | None = None

    @model_validator(mode="after")
    def validate_candidate_workflow_identity(
        self,
    ) -> "WorkflowBenchmarkExecutionCandidate":
        """Require candidate identity to reference the executed workflow."""

        if self.candidate_signature.workflow_id != self.workflow.id:
            raise ValueError(
                "Benchmark execution candidate signature must reference the executed workflow."
            )

        return self

    @model_validator(mode="after")
    def validate_unique_case_ids(
        self,
    ) -> "WorkflowBenchmarkExecutionCandidate":
        """Ensure one candidate executes each benchmark case at most once."""

        case_ids = self.case_ids

        if len(case_ids) != len(set(case_ids)):
            raise ValueError(
                "Benchmark execution candidate cases must use unique case identifiers."
            )

        return self

    @property
    def case_ids(
        self,
    ) -> tuple[UUID, ...]:
        """Return executed case identifiers in dataset order."""

        return tuple(case.case_id for case in self.cases)

    @property
    def cases_run(self) -> int:
        """Return the number of executed benchmark cases."""

        return len(self.cases)

    @property
    def cases_passed(self) -> int:
        """Return the number of benchmark cases that passed evaluation."""

        return sum(case.passed for case in self.cases)

    @property
    def accuracy(self) -> float:
        """Return the fraction of benchmark cases that passed."""

        return self.cases_passed / self.cases_run

    @property
    def run_failures(self) -> int:
        """Return the number of cases judged as failed runs."""

        return sum(case.run_failure for case in self.cases)

    @property
    def judged_semantically(self) -> bool:
        """Return whether any executed case used the semantic comparison."""

        return any(case.comparison is OutcomeComparison.SEMANTIC for case in self.cases)

    @property
    def judge_calls(self) -> int:
        """Return how many semantic judge calls judging this candidate made."""

        return sum(case.judge_calls for case in self.cases)

    @property
    def judge_cost_usd(self) -> float:
        """Return the judges' cost, which is never charged to the candidate."""

        return sum(case.judge_cost_usd for case in self.cases)

    @property
    def comparison_tallies(
        self,
    ) -> tuple[WorkflowBenchmarkComparisonTally, ...]:
        """Return pass counts per comparison, in comparison declaration order.

        Comparisons used by no executed case are omitted.
        """

        tallies: list[WorkflowBenchmarkComparisonTally] = []

        for comparison in OutcomeComparison:
            judged = [case for case in self.cases if case.comparison is comparison]

            if not judged:
                continue

            tallies.append(
                WorkflowBenchmarkComparisonTally(
                    comparison=comparison,
                    cases_run=len(judged),
                    cases_passed=sum(case.passed for case in judged),
                )
            )

        return tuple(tallies)

    def case(
        self,
        case_id: UUID,
    ) -> WorkflowBenchmarkExecutionCase | None:
        """Return the execution of one benchmark case."""

        return next(
            (case for case in self.cases if case.case_id == case_id),
            None,
        )

    def case_for_run(
        self,
        run_id: UUID,
    ) -> WorkflowBenchmarkExecutionCase | None:
        """Return the case executed through one workflow run."""

        return next(
            (case for case in self.cases if case.run_id == run_id),
            None,
        )


class WorkflowBenchmarkExecutionRecord(BaseModel):
    """Record one durable execution of a benchmark.

    A `run` record holds exactly one unscored candidate. A `compare` record
    holds at least two scored candidates judged on the same cases, the
    scoring policy that scored them, and a ranking of candidate identifiers,
    best first.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    benchmark_id: UUID

    benchmark_digest: str | None = Field(
        default=None,
        pattern=CONTENT_DIGEST_PATTERN,
    )

    kind: WorkflowBenchmarkExecutionKind

    candidates: tuple[
        WorkflowBenchmarkExecutionCandidate,
        ...,
    ] = Field(
        min_length=1,
    )

    ranking: tuple[UUID, ...] = ()

    scoring_policy: WorkflowScoringPolicy | None = None

    recorded_at: datetime = Field(
        default_factory=utc_now,
    )

    @model_validator(mode="after")
    def validate_unique_candidate_ids(
        self,
    ) -> "WorkflowBenchmarkExecutionRecord":
        """Ensure every candidate has a distinct identity."""

        candidate_ids = tuple(candidate.id for candidate in self.candidates)

        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError(
                "Benchmark execution candidates must use unique candidate identifiers."
            )

        return self

    @model_validator(mode="after")
    def validate_unique_run_ids(
        self,
    ) -> "WorkflowBenchmarkExecutionRecord":
        """Ensure every case across all candidates represents a distinct execution."""

        run_ids = tuple(case.run_id for candidate in self.candidates for case in candidate.cases)

        if len(run_ids) != len(set(run_ids)):
            raise ValueError("Benchmark execution cases must use unique run identifiers.")

        return self

    @model_validator(mode="after")
    def validate_unique_evaluation_ids(
        self,
    ) -> "WorkflowBenchmarkExecutionRecord":
        """Ensure every case across all candidates references a distinct evaluation."""

        evaluation_ids = tuple(
            case.evaluation_id for candidate in self.candidates for case in candidate.cases
        )

        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("Benchmark execution cases must use unique evaluation identifiers.")

        return self

    @model_validator(mode="after")
    def validate_kind_shape(
        self,
    ) -> "WorkflowBenchmarkExecutionRecord":
        """Require the candidates, ranking, and policy each kind produces."""

        if self.kind is WorkflowBenchmarkExecutionKind.RUN:
            self._validate_run_shape()
        else:
            self._validate_compare_shape()

        return self

    def _validate_run_shape(
        self,
    ) -> None:
        """Require one unscored, unranked candidate.

        Raises:
            ValueError: The record does not have the shape of a run.
        """

        if len(self.candidates) != 1:
            raise ValueError("Benchmark run executions must record exactly one candidate.")

        if self.ranking:
            raise ValueError("Benchmark run executions cannot record a ranking.")

        if self.scoring_policy is not None:
            raise ValueError("Benchmark run executions cannot record a scoring policy.")

        if self.candidates[0].scorecard is not None:
            raise ValueError("Benchmark run executions cannot record a scorecard.")

    def _validate_compare_shape(
        self,
    ) -> None:
        """Require scored candidates on identical cases and a complete ranking.

        Raises:
            ValueError: The record does not have the shape of a comparison.
        """

        if len(self.candidates) < 2:
            raise ValueError("Benchmark compare executions must record at least two candidates.")

        if self.scoring_policy is None:
            raise ValueError("Benchmark compare executions must record their scoring policy.")

        if any(candidate.scorecard is None for candidate in self.candidates):
            raise ValueError("Benchmark compare executions must record every candidate scorecard.")

        case_ids = self.candidates[0].case_ids

        if any(candidate.case_ids != case_ids for candidate in self.candidates):
            raise ValueError(
                "Benchmark compare execution candidates must be judged on the same cases."
            )

        if len(self.ranking) != len(set(self.ranking)):
            raise ValueError(
                "Benchmark execution ranking cannot contain duplicate candidate identifiers."
            )

        if set(self.ranking) != {candidate.id for candidate in self.candidates}:
            raise ValueError(
                "Benchmark execution ranking must reference every candidate exactly once."
            )

    @property
    def case_ids(
        self,
    ) -> tuple[UUID, ...]:
        """Return the executed case identifiers in dataset order."""

        return self.candidates[0].case_ids

    @property
    def ranked_candidates(
        self,
    ) -> tuple[WorkflowBenchmarkExecutionCandidate, ...]:
        """Return every candidate in rank order, best first.

        A run's single candidate is returned as it was recorded.
        """

        if not self.ranking:
            return self.candidates

        candidates = {candidate.id: candidate for candidate in self.candidates}

        return tuple(candidates[candidate_id] for candidate_id in self.ranking)

    @property
    def winner(
        self,
    ) -> WorkflowBenchmarkExecutionCandidate | None:
        """Return the highest-ranked candidate, or None for an unranked run."""

        if not self.ranking:
            return None

        return self.ranked_candidates[0]

    @property
    def judge_calls(self) -> int:
        """Return how many semantic judge calls the whole execution made."""

        return sum(candidate.judge_calls for candidate in self.candidates)

    @property
    def judge_cost_usd(self) -> float:
        """Return the judges' cost across the whole execution."""

        return sum(candidate.judge_cost_usd for candidate in self.candidates)

    def candidate(
        self,
        candidate_id: UUID,
    ) -> WorkflowBenchmarkExecutionCandidate | None:
        """Return one candidate by its identifier."""

        return next(
            (candidate for candidate in self.candidates if candidate.id == candidate_id),
            None,
        )

    def candidate_for_run(
        self,
        run_id: UUID,
    ) -> WorkflowBenchmarkExecutionCandidate | None:
        """Return the candidate whose cases include one workflow run."""

        return next(
            (
                candidate
                for candidate in self.candidates
                if candidate.case_for_run(run_id) is not None
            ),
            None,
        )

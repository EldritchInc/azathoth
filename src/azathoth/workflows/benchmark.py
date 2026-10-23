"""Execution, scoring, comparison, and ranking for workflow benchmarks."""

from collections.abc import Callable, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    EvaluationResult,
    OutcomeComparison,
    OutcomeEvaluator,
)
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.execution import WorkflowRun
from azathoth.workflows.input import (
    create_workflow_input_event,
)
from azathoth.workflows.ranker import WorkflowRanker
from azathoth.workflows.result import (
    WorkflowResultError,
    workflow_result,
)
from azathoth.workflows.run_failure import (
    RUN_FAILURE_EVALUATOR_NAME,
    evaluate_failed_run,
)
from azathoth.workflows.runner import WorkflowRunner
from azathoth.workflows.scorecard import WorkflowScorecard
from azathoth.workflows.scoring import (
    WorkflowScorer,
    WorkflowScoringPolicy,
)
from azathoth.workflows.value import WorkflowValueReference


class WorkflowBenchmarkCaseResult(BaseModel):
    """Recorded benchmark evidence for one workflow execution."""

    model_config = ConfigDict(frozen=True)

    case_id: UUID
    comparison: OutcomeComparison
    run: WorkflowRun
    evaluation: EvaluationResult


class WorkflowBenchmarkComparisonTally(BaseModel):
    """Pass counts for the benchmark cases judged by one comparison."""

    model_config = ConfigDict(frozen=True)

    comparison: OutcomeComparison
    cases_run: int = Field(ge=0)
    cases_passed: int = Field(ge=0)


class WorkflowBenchmarkResult(BaseModel):
    """Aggregate result of executing one benchmark dataset."""

    model_config = ConfigDict(frozen=True)

    dataset_id: UUID
    cases: tuple[WorkflowBenchmarkCaseResult, ...] = ()

    @property
    def cases_run(self) -> int:
        """Return the number of executed benchmark cases."""

        return len(self.cases)

    @property
    def cases_passed(self) -> int:
        """Return the number of benchmark cases that passed evaluation."""

        return sum(case.evaluation.passed for case in self.cases)

    @property
    def run_failures(self) -> int:
        """Return the number of cases judged as failed runs.

        A case is a run failure when its run failed without producing the
        declared result. Runs whose steps failed but which still produced the
        declared result are judged normally and are not counted here.
        """

        return sum(
            case.evaluation.evaluator_name == RUN_FAILURE_EVALUATOR_NAME for case in self.cases
        )

    @property
    def accuracy(self) -> float:
        """Return the fraction of benchmark cases that passed."""

        if not self.cases:
            return 0.0

        return self.cases_passed / self.cases_run

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
                    cases_passed=sum(case.evaluation.passed for case in judged),
                )
            )

        return tuple(tallies)

    @property
    def total_tokens(self) -> int:
        """Return total recorded token usage across benchmark executions."""

        return sum(
            metrics.total_tokens
            for case in self.cases
            for step in case.run.steps
            if step.execution is not None
            if step.execution.metrics is not None
            if (metrics := step.execution.metrics).total_tokens is not None
        )

    @property
    def total_cost_usd(self) -> float:
        """Return total recorded model cost across benchmark executions."""

        return sum(
            metrics.estimated_cost_usd
            for case in self.cases
            for step in case.run.steps
            if step.execution is not None
            if step.execution.metrics is not None
            if (metrics := step.execution.metrics).estimated_cost_usd is not None
        )

    @property
    def total_latency_ms(self) -> int:
        """Return total recorded provider latency across benchmark executions."""

        return sum(
            metrics.latency_ms
            for case in self.cases
            for step in case.run.steps
            if step.execution is not None
            if step.execution.metrics is not None
            if (metrics := step.execution.metrics).latency_ms is not None
        )


class WorkflowBenchmarkComparisonEntry(BaseModel):
    """Benchmark evidence recorded for one named workflow candidate."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    result: WorkflowBenchmarkResult


class WorkflowBenchmarkComparison(BaseModel):
    """Side-by-side benchmark evidence for multiple workflow candidates."""

    model_config = ConfigDict(frozen=True)

    dataset_id: UUID
    candidates: tuple[WorkflowBenchmarkComparisonEntry, ...] = ()

    @model_validator(mode="after")
    def validate_unique_candidate_names(
        self,
    ) -> "WorkflowBenchmarkComparison":
        """Reject duplicate benchmark candidate names."""

        names = tuple(candidate.name for candidate in self.candidates)

        if len(names) != len(set(names)):
            raise ValueError(
                "Workflow benchmark comparison cannot contain duplicate candidate names."
            )

        return self

    def get(
        self,
        name: str,
    ) -> WorkflowBenchmarkResult | None:
        """Return benchmark evidence for one named candidate."""

        return next(
            (candidate.result for candidate in self.candidates if candidate.name == name),
            None,
        )


class WorkflowBenchmarkCandidateScorecard(BaseModel):
    """Aggregate workflow scorecard for one benchmark candidate."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    scorecard: WorkflowScorecard


class WorkflowBenchmarkRankedCandidate(BaseModel):
    """A named benchmark candidate assigned a deterministic rank."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    name: str = Field(min_length=1)
    scorecard: WorkflowScorecard


class WorkflowBenchmarkRanking(BaseModel):
    """Ordered benchmark ranking using workflow scorecard evidence."""

    model_config = ConfigDict(frozen=True)

    entries: tuple[WorkflowBenchmarkRankedCandidate, ...] = Field(
        min_length=1,
    )

    @property
    def winner(self) -> WorkflowBenchmarkRankedCandidate:
        """Return the highest-ranked benchmark candidate."""

        return self.entries[0]


class WorkflowBenchmarkRunner:
    """Execute workflow candidates across durable benchmark datasets."""

    def __init__(
        self,
        runner: WorkflowRunner | None = None,
        evaluator: OutcomeEvaluator | None = None,
    ) -> None:
        self._runner = runner if runner is not None else WorkflowRunner()
        self._evaluator = evaluator if evaluator is not None else OutcomeEvaluator()

    async def run(
        self,
        dataset: BenchmarkDataset,
        candidate_factory: Callable[
            [BenchmarkCase],
            WorkflowCandidate,
        ],
    ) -> WorkflowBenchmarkResult:
        """Execute and evaluate every case in a benchmark dataset.

        Every case judges the candidate's declared result with the evaluator
        for the case's own comparison. All comparisons are checked before any
        case executes, so a dataset containing an unsupported comparison never
        partially runs.

        Failed runs never abort the benchmark. A run that produced its declared
        result is judged on it even when some of its steps failed, because
        workflows may tolerate step failures by design. A failed run that did
        not produce its declared result is recorded with a failing run-failure
        evaluation.

        Raises:
            UnsupportedComparisonError: A case uses a comparison with no
                evaluator.
            WorkflowResultError: A candidate declares no result, a successful
                run did not produce its declared result, or a run produced it
                more than once.
        """

        for case in dataset.cases:
            self._evaluator.require_supported(
                case.expected.comparison,
                subject=f"Benchmark case {case.id}",
            )

        results: list[WorkflowBenchmarkCaseResult] = []

        for case in dataset.cases:
            candidate = candidate_factory(
                case,
            )

            if candidate.result is None:
                raise WorkflowResultError(
                    f"Workflow {candidate.metadata.id} does not declare a result."
                )

            context = Context(
                events=(
                    create_workflow_input_event(
                        case.input,
                        producer="azathoth.benchmark",
                    ),
                )
            )

            run = await self._runner.run_recording_failures(
                candidate,
                context,
            )

            evaluation = await self._evaluate_case(
                case=case,
                run=run,
                result=candidate.result,
            )

            results.append(
                WorkflowBenchmarkCaseResult(
                    case_id=case.id,
                    comparison=case.expected.comparison,
                    run=run,
                    evaluation=evaluation,
                )
            )

        return WorkflowBenchmarkResult(
            dataset_id=dataset.id,
            cases=tuple(results),
        )

    async def _evaluate_case(
        self,
        *,
        case: BenchmarkCase,
        run: WorkflowRun,
        result: WorkflowValueReference,
    ) -> EvaluationResult:
        """Judge one case's run on its declared result.

        Raises:
            WorkflowResultError: A successful run did not produce its declared
                result, or a run produced it more than once.
        """

        produced = any(
            value.name == result.name
            for value in run.values_from(
                result.producer_step_id,
            )
        )

        if run.failed and not produced:
            return evaluate_failed_run(
                run,
                case.expected,
            )

        try:
            actual = workflow_result(
                run,
                result,
            )
        except WorkflowResultError as exc:
            raise WorkflowResultError(f"Benchmark case {case.id}: {exc}") from exc

        return await self._evaluator.evaluate(
            case.expected,
            actual,
        )


class WorkflowBenchmarkComparator:
    """Compare named workflow candidates against one benchmark dataset."""

    def __init__(
        self,
        runner: WorkflowBenchmarkRunner | None = None,
    ) -> None:
        self._runner = runner if runner is not None else WorkflowBenchmarkRunner()

    async def compare(
        self,
        dataset: BenchmarkDataset,
        candidate_factories: Mapping[
            str,
            Callable[[BenchmarkCase], WorkflowCandidate],
        ],
    ) -> WorkflowBenchmarkComparison:
        """Execute every named candidate factory against one dataset."""

        candidates: list[WorkflowBenchmarkComparisonEntry] = []

        for name, candidate_factory in candidate_factories.items():
            result = await self._runner.run(
                dataset,
                candidate_factory,
            )

            candidates.append(
                WorkflowBenchmarkComparisonEntry(
                    name=name,
                    result=result,
                )
            )

        return WorkflowBenchmarkComparison(
            dataset_id=dataset.id,
            candidates=tuple(candidates),
        )


class WorkflowBenchmarkScorer:
    """Aggregate workflow scorecards across benchmark cases."""

    def __init__(
        self,
        *,
        policy: WorkflowScoringPolicy,
    ) -> None:
        self._scorer = WorkflowScorer(
            policy=policy,
        )

    def score(
        self,
        candidate: WorkflowBenchmarkComparisonEntry,
    ) -> WorkflowBenchmarkCandidateScorecard:
        """Score one benchmark candidate across all executed cases."""

        if not candidate.result.cases:
            raise ValueError("Cannot score a benchmark candidate with no executed cases.")

        case_scorecards = tuple(
            self._scorer.score(
                run=case.run,
                evaluation=case.evaluation,
            )
            for case in candidate.result.cases
        )

        count = len(case_scorecards)

        scorecard = WorkflowScorecard(
            quality_score=sum(item.quality_score for item in case_scorecards) / count,
            reliability_score=sum(item.reliability_score for item in case_scorecards) / count,
            latency_score=sum(item.latency_score for item in case_scorecards) / count,
            cost_score=sum(item.cost_score for item in case_scorecards) / count,
            overall_score=sum(item.overall_score for item in case_scorecards) / count,
            rationale=(
                f"Benchmark aggregate for candidate {candidate.name!r} across {count} cases."
            ),
        )

        return WorkflowBenchmarkCandidateScorecard(
            name=candidate.name,
            scorecard=scorecard,
        )


class WorkflowBenchmarkRanker:
    """Rank benchmark candidates using the canonical workflow ranker."""

    def __init__(
        self,
        *,
        scorer: WorkflowBenchmarkScorer,
        ranker: WorkflowRanker | None = None,
    ) -> None:
        self._scorer = scorer
        self._ranker = ranker if ranker is not None else WorkflowRanker()

    def rank(
        self,
        comparison: WorkflowBenchmarkComparison,
    ) -> WorkflowBenchmarkRanking:
        """Score and rank benchmark candidates deterministically."""

        if not comparison.candidates:
            raise ValueError("At least one benchmark candidate is required for ranking.")

        scored_candidates = tuple(
            self._scorer.score(candidate) for candidate in comparison.candidates
        )

        ranking = self._ranker.rank(tuple(candidate.scorecard for candidate in scored_candidates))

        entries: list[WorkflowBenchmarkRankedCandidate] = []

        for ranked in ranking.entries:
            candidate = next(
                candidate
                for candidate in scored_candidates
                if candidate.scorecard == ranked.scorecard
            )

            entries.append(
                WorkflowBenchmarkRankedCandidate(
                    rank=ranked.rank,
                    name=candidate.name,
                    scorecard=ranked.scorecard,
                )
            )

        return WorkflowBenchmarkRanking(
            entries=tuple(entries),
        )

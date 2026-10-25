"""Tests for benchmark execution when workflow runs fail."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import (
    Strategy,
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    RUN_FAILURE_EVALUATOR_NAME,
    WorkflowBenchmarkComparator,
    WorkflowBenchmarkRanker,
    WorkflowBenchmarkRunner,
    WorkflowBenchmarkScorer,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowCondition,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowResultError,
    WorkflowRunner,
    WorkflowScoringPolicy,
    WorkflowValueBinding,
    WorkflowValueReference,
)

DATASET_ID = UUID("a1111111-1111-4111-8111-111111111111")

PASSING_CASE_ID = UUID("a2222222-2222-4222-8222-222222222222")

FAILING_CASE_ID = UUID("a3333333-3333-4333-8333-333333333333")

WORKFLOW_ID = UUID("a4444444-4444-4444-8444-444444444444")

ANSWER_STEP_ID = UUID("a5555555-5555-4555-8555-555555555555")

HELPER_STEP_ID = UUID("a6666666-6666-4666-8666-666666666666")

FAILING = "Failing"

ANSWER = "positive"


class StubStrategy:
    """A strategy whose output is its own name."""

    def __init__(
        self,
        *,
        name: str,
    ) -> None:
        self._metadata = StrategyMetadata(
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return self._metadata

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Return the strategy name as output."""

        return StrategyOutcome(
            output=self.metadata.name,
        )


class SelectiveFailureExecutor(StrategyExecutor):
    """Fail every strategy named Failing and execute all others."""

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Execute or fail the supplied strategy."""

        if strategy.metadata.name == FAILING:
            raise RuntimeError("Provider unavailable.")

        now = datetime(
            2026,
            10,
            22,
            12,
            0,
            tzinfo=UTC,
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=strategy.metadata.name,
            metrics=StrategyExecutionMetrics(
                provider="test-provider",
                model="test-model",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                latency_ms=0,
                estimated_cost_usd=0.0,
            ),
            initial_context=context,
            final_context=context,
            started_at=now,
            completed_at=now,
        )


def create_benchmark_runner() -> WorkflowBenchmarkRunner:
    """Create a benchmark runner backed by the selective failure executor."""

    return WorkflowBenchmarkRunner(
        runner=WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ),
    )


def create_dataset() -> BenchmarkDataset:
    """Create a benchmark with one passing case and one failing case."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="run-failures",
        description="Benchmark whose second case fails its run.",
        cases=(
            BenchmarkCase(
                id=PASSING_CASE_ID,
                input="first",
                expected=ExpectedOutcome(
                    description="The answer.",
                    value=ANSWER,
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            BenchmarkCase(
                id=FAILING_CASE_ID,
                input="second",
                expected=ExpectedOutcome(
                    description="The answer.",
                    value=ANSWER,
                    comparison=OutcomeComparison.NORMALIZED,
                ),
            ),
        ),
    )


def create_metadata() -> WorkflowMetadata:
    """Create the shared workflow metadata."""

    return WorkflowMetadata(
        id=WORKFLOW_ID,
        name="Run failure workflow",
        description="Exercise benchmark run failures.",
    )


def create_answer_result() -> WorkflowValueReference:
    """Reference the answer step's declared output."""

    return WorkflowValueReference(
        producer_step_id=ANSWER_STEP_ID,
        name="answer",
    )


def create_single_step_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create a one-step candidate whose step fails on the failing case."""

    return WorkflowCandidate(
        metadata=create_metadata(),
        steps=(
            WorkflowCandidateStep(
                id=ANSWER_STEP_ID,
                strategy=StubStrategy(
                    name=(FAILING if case.id == FAILING_CASE_ID else ANSWER),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="answer",
                    ),
                ),
            ),
        ),
        result=create_answer_result(),
    )


def create_tolerant_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create a candidate whose helper step fails without blocking the answer."""

    return WorkflowCandidate(
        metadata=create_metadata(),
        steps=(
            WorkflowCandidateStep(
                id=HELPER_STEP_ID,
                strategy=StubStrategy(
                    name=FAILING,
                ),
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            WorkflowCandidateStep(
                id=ANSWER_STEP_ID,
                strategy=StubStrategy(
                    name=ANSWER,
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="answer",
                    ),
                ),
            ),
        ),
        result=create_answer_result(),
    )


def create_blocked_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create a candidate whose failed helper skips the answer step."""

    return WorkflowCandidate(
        metadata=create_metadata(),
        steps=(
            WorkflowCandidateStep(
                id=HELPER_STEP_ID,
                strategy=StubStrategy(
                    name=FAILING,
                ),
                failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
            ),
            WorkflowCandidateStep(
                id=ANSWER_STEP_ID,
                strategy=StubStrategy(
                    name=ANSWER,
                ),
                depends_on=(HELPER_STEP_ID,),
                outputs=(
                    WorkflowValueBinding(
                        name="answer",
                    ),
                ),
            ),
        ),
        result=create_answer_result(),
    )


def create_skipped_result_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create a successful candidate whose condition skips the answer step."""

    return WorkflowCandidate(
        metadata=create_metadata(),
        steps=(
            WorkflowCandidateStep(
                id=HELPER_STEP_ID,
                strategy=StubStrategy(
                    name="Route",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="route",
                    ),
                ),
            ),
            WorkflowCandidateStep(
                id=ANSWER_STEP_ID,
                strategy=StubStrategy(
                    name=ANSWER,
                ),
                depends_on=(HELPER_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=HELPER_STEP_ID,
                            name="route",
                        ),
                        expected="never",
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="answer",
                    ),
                ),
            ),
        ),
        result=create_answer_result(),
    )


def test_failed_run_counts_as_failed_case_without_aborting() -> None:
    """A failed run is recorded as a failed case and later cases still run."""

    result = asyncio.run(
        create_benchmark_runner().run(
            create_dataset(),
            create_single_step_candidate,
        )
    )

    assert tuple(case.case_id for case in result.cases) == (
        PASSING_CASE_ID,
        FAILING_CASE_ID,
    )
    assert result.cases_run == 2
    assert result.cases_passed == 1
    assert result.accuracy == 0.5
    assert result.run_failures == 1


def test_failed_run_is_judged_by_run_failure_evaluation() -> None:
    """The failed case carries the run-failure evaluation and its failed run."""

    result = asyncio.run(
        create_benchmark_runner().run(
            create_dataset(),
            create_single_step_candidate,
        )
    )

    failed_case = result.cases[1]

    assert failed_case.run.failed
    assert failed_case.comparison is OutcomeComparison.NORMALIZED
    assert failed_case.evaluation.evaluator_name == RUN_FAILURE_EVALUATOR_NAME
    assert not failed_case.evaluation.passed
    assert failed_case.evaluation.reason == (
        f"Workflow run failed at step {ANSWER_STEP_ID}: Provider unavailable."
    )


def test_failed_run_counts_against_its_comparison_tally() -> None:
    """A failed run counts as a failed case of its own comparison."""

    result = asyncio.run(
        create_benchmark_runner().run(
            create_dataset(),
            create_single_step_candidate,
        )
    )

    assert tuple(
        (tally.comparison, tally.cases_passed, tally.cases_run)
        for tally in result.comparison_tallies
    ) == (
        (OutcomeComparison.EXACT, 1, 1),
        (OutcomeComparison.NORMALIZED, 0, 1),
    )


def test_tolerated_step_failure_is_judged_on_result() -> None:
    """A run whose failed step was tolerated is judged on its declared result."""

    result = asyncio.run(
        create_benchmark_runner().run(
            create_dataset(),
            create_tolerant_candidate,
        )
    )

    assert all(case.run.succeeded for case in result.cases)
    assert all(case.run.failed_step_count == 1 for case in result.cases)
    assert all(case.evaluation.passed for case in result.cases)
    assert all(
        case.evaluation.evaluator_name != RUN_FAILURE_EVALUATOR_NAME for case in result.cases
    )
    assert result.accuracy == 1.0
    assert result.run_failures == 0


def test_failure_that_blocks_result_is_run_failure() -> None:
    """A failed step that prevents the declared result is a run failure."""

    result = asyncio.run(
        create_benchmark_runner().run(
            create_dataset(),
            create_blocked_candidate,
        )
    )

    assert result.cases_passed == 0
    assert result.run_failures == 2
    assert all(
        case.evaluation.reason
        == f"Workflow run failed at step {HELPER_STEP_ID}: Provider unavailable."
        for case in result.cases
    )


def test_successful_run_without_result_still_raises() -> None:
    """A successful run that skipped its result producer is still an error."""

    with pytest.raises(
        WorkflowResultError,
    ) as error:
        asyncio.run(
            create_benchmark_runner().run(
                create_dataset(),
                create_skipped_result_candidate,
            )
        )

    assert str(error.value) == (
        f"Benchmark case {PASSING_CASE_ID}: Workflow result 'answer' from step "
        f"{ANSWER_STEP_ID} was not produced."
    )


def test_benchmark_result_with_run_failures_round_trips_through_json() -> None:
    """Run-failure cases survive JSON round trips."""

    result = asyncio.run(
        create_benchmark_runner().run(
            create_dataset(),
            create_single_step_candidate,
        )
    )

    restored = type(result).model_validate_json(
        result.model_dump_json(),
    )

    assert restored == result
    assert restored.run_failures == 1


def test_comparison_ranks_candidates_with_failed_runs() -> None:
    """Comparing and ranking count failed runs against the candidate."""

    benchmark_runner = create_benchmark_runner()

    comparison = asyncio.run(
        WorkflowBenchmarkComparator(
            runner=benchmark_runner,
        ).compare(
            create_dataset(),
            {
                "flaky": create_single_step_candidate,
                "tolerant": create_tolerant_candidate,
            },
        )
    )

    assert tuple(
        (entry.name, entry.result.accuracy, entry.result.run_failures)
        for entry in comparison.candidates
    ) == (
        ("flaky", 0.5, 1),
        ("tolerant", 1.0, 0),
    )

    ranking = WorkflowBenchmarkRanker(
        scorer=WorkflowBenchmarkScorer(
            policy=WorkflowScoringPolicy(
                target_latency_seconds=10.0,
                target_cost_usd=1.0,
            ),
        ),
    ).rank(
        comparison,
    )

    assert ranking.winner.name == "tolerant"

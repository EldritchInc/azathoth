"""Tests for workflow experiment orchestration."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    EvaluationResult,
    EvaluationStatus,
    Evaluator,
    EvaluatorMetadata,
    ExpectedOutcome,
    OutcomeComparison,
    OutcomeEvaluator,
    UnsupportedComparisonError,
)
from azathoth.strategies import (
    Strategy,
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowExperimentResult,
    WorkflowExperimentRunner,
    WorkflowMetadata,
    WorkflowScorer,
    WorkflowScoringPolicy,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID_A = UUID("11111111-1111-1111-1111-111111111111")

WORKFLOW_ID_B = UUID("22222222-2222-2222-2222-222222222222")

WORKFLOW_ID_C = UUID("33333333-3333-3333-3333-333333333333")

STEP_ID_A = UUID("44444444-4444-4444-4444-444444444444")

STEP_ID_B = UUID("55555555-5555-5555-5555-555555555555")

STEP_ID_C = UUID("66666666-6666-6666-6666-666666666666")

STRATEGY_ID_A = UUID("77777777-7777-7777-7777-777777777777")

STRATEGY_ID_B = UUID("88888888-8888-8888-8888-888888888888")

STRATEGY_ID_C = UUID("99999999-9999-9999-9999-999999999999")

DATASET_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

CASE_ID_A = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1")

CASE_ID_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2")

CASE_ID_C = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3")


class StaticStrategy:
    """Return one configured deterministic strategy outcome."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        output: str,
        estimated_cost_usd: float,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=f"strategy-{strategy_id}",
            description="Deterministic workflow experiment strategy.",
        )
        self._output = output
        self._estimated_cost_usd = estimated_cost_usd
        self.calls = 0

    @property
    def metadata(self) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return self._metadata

    async def run(
        self,
        _context: Context,
    ) -> StrategyOutcome:
        """Return the configured strategy outcome."""

        self.calls += 1

        return StrategyOutcome(
            output=self._output,
            metrics=StrategyExecutionMetrics(
                provider="test-provider",
                model="test-model",
                prompt_tokens=10,
                completion_tokens=1,
                total_tokens=11,
                latency_ms=100,
                estimated_cost_usd=self._estimated_cost_usd,
            ),
        )


class FailingStrategy:
    """Raise one configured deterministic execution failure."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        message: str,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=f"failing-strategy-{strategy_id}",
            description="Deterministic failing workflow experiment strategy.",
        )
        self._message = message
        self.calls = 0

    @property
    def metadata(self) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return self._metadata

    async def run(
        self,
        _context: Context,
    ) -> StrategyOutcome:
        """Raise the configured execution failure."""

        self.calls += 1

        raise RuntimeError(
            self._message,
        )


class RecordingEvaluator:
    """Record evaluated outputs and score exact expected matches."""

    def __init__(self) -> None:
        self._metadata = EvaluatorMetadata(
            name="recording-evaluator",
            description="Record workflow experiment evaluations.",
        )
        self.actual_values: list[object] = []

    @property
    def metadata(self) -> EvaluatorMetadata:
        """Return deterministic evaluator metadata."""

        return self._metadata

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: object,
    ) -> EvaluationResult:
        """Record and evaluate one workflow output."""

        self.actual_values.append(actual)

        passed = actual == expected.value

        return EvaluationResult(
            evaluator_name=self.metadata.name,
            evaluator_version=self.metadata.version,
            score=1.0 if passed else 0.0,
            threshold=1.0,
            status=(EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED),
            reason=(
                "Actual value matched expected value."
                if passed
                else "Actual value did not match expected value."
            ),
        )


def create_workflow(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy: Strategy,
    name: str,
) -> WorkflowCandidate:
    """Create a deterministic one-step workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=name,
            description="Workflow used for experiment runner tests.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=step_id,
                strategy=strategy,
                outputs=(
                    WorkflowValueBinding(
                        name="answer",
                    ),
                ),
            ),
        ),
        result=WorkflowValueReference(
            producer_step_id=step_id,
            name="answer",
        ),
    )


def create_scorer() -> WorkflowScorer:
    """Create the canonical workflow scorer used by tests."""

    return WorkflowScorer(
        policy=WorkflowScoringPolicy(
            target_latency_seconds=60.0,
            target_cost_usd=0.10,
        ),
    )


def create_expected_outcome() -> ExpectedOutcome:
    """Create the expected experiment outcome."""

    return ExpectedOutcome(
        description="Workflow should return success.",
        value="success",
        comparison=OutcomeComparison.EXACT,
    )


def create_dataset() -> BenchmarkDataset:
    """Create a one-case benchmark expecting success."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="experiment-runner",
        description="Benchmark used for experiment runner tests.",
        cases=(
            BenchmarkCase(
                id=CASE_ID_A,
                input="request",
                expected=create_expected_outcome(),
            ),
        ),
    )


def create_case(
    *,
    case_id: UUID,
    input_value: str,
    expected_value: str,
    comparison: OutcomeComparison = OutcomeComparison.EXACT,
) -> BenchmarkCase:
    """Create one deterministic benchmark case."""

    return BenchmarkCase(
        id=case_id,
        input=input_value,
        expected=ExpectedOutcome(
            description=f"Workflow should return {expected_value}.",
            value=expected_value,
            comparison=comparison,
        ),
    )


def create_multi_case_dataset(
    *cases: BenchmarkCase,
) -> BenchmarkDataset:
    """Create a benchmark from explicit cases."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="experiment-runner-multi-case",
        description="Multi-case benchmark used for experiment runner tests.",
        cases=cases,
    )


def create_outcome_evaluator(
    evaluator: Evaluator,
) -> OutcomeEvaluator:
    """Route exact comparisons to one test evaluator."""

    return OutcomeEvaluator(
        {
            OutcomeComparison.EXACT: evaluator,
        }
    )


class EchoInputStrategy:
    """Return the benchmark input received through the workflow context."""

    def __init__(self) -> None:
        self._metadata = StrategyMetadata(
            id=STRATEGY_ID_A,
            name="echo-input",
            description="Echo the workflow input.",
        )
        self.inputs: list[object] = []

    @property
    def metadata(self) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return self._metadata

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Return the received workflow input as output."""

        event = context.latest(
            WORKFLOW_INPUT_EVENT_TYPE,
        )

        assert event is not None

        value = event.payload["input"]

        self.inputs.append(value)

        return StrategyOutcome(
            output=value,
            metrics=StrategyExecutionMetrics(
                provider="test-provider",
                model="test-model",
                prompt_tokens=10,
                completion_tokens=1,
                total_tokens=11,
                latency_ms=100,
                estimated_cost_usd=0.05,
            ),
        )


def test_experiment_runner_executes_every_workflow() -> None:
    """Every candidate workflow should execute exactly once."""

    strategy_a = StaticStrategy(
        strategy_id=STRATEGY_ID_A,
        output="success",
        estimated_cost_usd=0.05,
    )

    strategy_b = StaticStrategy(
        strategy_id=STRATEGY_ID_B,
        output="failure",
        estimated_cost_usd=0.05,
    )

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=strategy_a,
            name="workflow-a",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=strategy_b,
            name="workflow-b",
        ),
    )

    asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(RecordingEvaluator()),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert strategy_a.calls == 1
    assert strategy_b.calls == 1


def test_experiment_runner_evaluates_every_workflow_output() -> None:
    """Every candidate's successful output should be evaluated."""

    evaluator = RecordingEvaluator()

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="workflow-a",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_B,
                output="failure",
                estimated_cost_usd=0.05,
            ),
            name="workflow-b",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_C,
            step_id=STEP_ID_C,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_C,
                output="other",
                estimated_cost_usd=0.05,
            ),
            name="workflow-c",
        ),
    )

    asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(evaluator),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert evaluator.actual_values == [
        "success",
        "failure",
        "other",
    ]


def test_experiment_runner_produces_scorecard_for_every_workflow() -> None:
    """Every executed workflow should produce one scorecard."""

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="workflow-a",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_B,
                output="failure",
                estimated_cost_usd=0.05,
            ),
            name="workflow-b",
        ),
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(RecordingEvaluator()),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert len(result.scorecards) == 2


def test_experiment_runner_associates_scorecards_with_candidate_signatures() -> None:
    """Every scorecard should retain the resolved candidate that produced it."""

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="workflow-a",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_B,
                output="failure",
                estimated_cost_usd=0.05,
            ),
            name="workflow-b",
        ),
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(RecordingEvaluator()),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert tuple(observation.candidate_signature for observation in result.evidence) == (
        workflows[0].signature,
        workflows[1].signature,
    )

    assert tuple(observation.scorecard for observation in result.evidence) == result.scorecards


def test_experiment_runner_ranks_workflow_scorecards() -> None:
    """Experiment results should rank stronger scorecards first."""

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="failure",
                estimated_cost_usd=0.40,
            ),
            name="weakest",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_B,
                output="failure",
                estimated_cost_usd=0.05,
            ),
            name="middle",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_C,
            step_id=STEP_ID_C,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_C,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="strongest",
        ),
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(RecordingEvaluator()),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert tuple(entry.scorecard for entry in result.ranking.entries) == (
        result.scorecards[2],
        result.scorecards[1],
        result.scorecards[0],
    )


def test_experiment_runner_exposes_winner() -> None:
    """Experiment winner should be the highest-ranked scorecard."""

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="failure",
                estimated_cost_usd=0.40,
            ),
            name="weakest",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_B,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="winner",
        ),
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(RecordingEvaluator()),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert result.winner == result.scorecards[1]
    assert result.winner.quality_score == pytest.approx(1.0)
    assert result.winner.overall_score == pytest.approx(1.0)


def test_experiment_runner_preserves_input_order_for_exact_ties() -> None:
    """Exact score ties should retain candidate input order."""

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="first",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_B,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="second",
        ),
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(RecordingEvaluator()),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert result.ranking.entries[0].scorecard == result.scorecards[0]
    assert result.ranking.entries[1].scorecard == result.scorecards[1]


def test_experiment_runner_rejects_empty_workflow_collection() -> None:
    """Experiments require at least one candidate workflow."""

    with pytest.raises(
        ValueError,
        match="At least one workflow scorecard is required for ranking.",
    ):
        asyncio.run(
            WorkflowExperimentRunner(
                scorer=create_scorer(),
                evaluator=create_outcome_evaluator(RecordingEvaluator()),
            ).run(
                workflows=(),
                dataset=create_dataset(),
            )
        )


def test_experiment_runner_result_round_trips_through_json() -> None:
    """Produced experiment results should survive JSON serialization."""

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="winner",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_B,
                output="failure",
                estimated_cost_usd=0.05,
            ),
            name="runner-up",
        ),
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(RecordingEvaluator()),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    restored = WorkflowExperimentResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.winner == result.winner


def test_experiment_runner_continues_after_candidate_execution_failure() -> None:
    """One failed candidate should not prevent later candidates from executing."""

    strategy_a = StaticStrategy(
        strategy_id=STRATEGY_ID_A,
        output="failure",
        estimated_cost_usd=0.05,
    )
    strategy_b = FailingStrategy(
        strategy_id=STRATEGY_ID_B,
        message="candidate-b failed",
    )
    strategy_c = StaticStrategy(
        strategy_id=STRATEGY_ID_C,
        output="success",
        estimated_cost_usd=0.05,
    )

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=strategy_a,
            name="workflow-a",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=strategy_b,
            name="workflow-b",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_C,
            step_id=STEP_ID_C,
            strategy=strategy_c,
            name="workflow-c",
        ),
    )

    asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(RecordingEvaluator()),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert strategy_a.calls == 1
    assert strategy_b.calls == 1
    assert strategy_c.calls == 1


def test_experiment_runner_does_not_evaluate_failed_candidate() -> None:
    """A failed candidate has no successful output to evaluate."""

    evaluator = RecordingEvaluator()

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="failure",
                estimated_cost_usd=0.05,
            ),
            name="workflow-a",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=FailingStrategy(
                strategy_id=STRATEGY_ID_B,
                message="candidate-b failed",
            ),
            name="workflow-b",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_C,
            step_id=STEP_ID_C,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_C,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="workflow-c",
        ),
    )

    asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(evaluator),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert evaluator.actual_values == [
        "failure",
        "success",
    ]


def test_experiment_runner_ranks_successfully_executed_candidates_after_failure() -> None:
    """Failed execution should not prevent viable candidates from being ranked."""

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="failure",
                estimated_cost_usd=0.05,
            ),
            name="workflow-a",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=FailingStrategy(
                strategy_id=STRATEGY_ID_B,
                message="candidate-b failed",
            ),
            name="workflow-b",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_C,
            step_id=STEP_ID_C,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_C,
                output="success",
                estimated_cost_usd=0.05,
            ),
            name="workflow-c",
        ),
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(RecordingEvaluator()),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert len(result.scorecards) == 3

    assert tuple(observation.candidate_signature for observation in result.evidence) == (
        workflows[0].signature,
        workflows[1].signature,
        workflows[2].signature,
    )

    assert result.winner == result.scorecards[2]
    assert result.winner.quality_score == pytest.approx(1.0)


def test_experiment_runner_scores_failed_candidate_as_failed_case() -> None:
    """A failed candidate is ranked with zero quality behind successful runs."""

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=StaticStrategy(
                strategy_id=STRATEGY_ID_A,
                output="failure",
                estimated_cost_usd=0.05,
            ),
            name="workflow-a",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=FailingStrategy(
                strategy_id=STRATEGY_ID_B,
                message="candidate-b failed",
            ),
            name="workflow-b",
        ),
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    failed = result.evidence[1].scorecard

    assert failed.quality_score == 0.0
    assert failed.reliability_score < result.evidence[0].scorecard.reliability_score
    assert tuple(evidence.candidate_signature for evidence in result.ranked_evidence) == (
        workflows[0].signature,
        workflows[1].signature,
    )


def test_experiment_runner_ranks_population_when_every_candidate_fails() -> None:
    """A generation in which every run failed still ranks every candidate."""

    workflows = (
        create_workflow(
            workflow_id=WORKFLOW_ID_A,
            step_id=STEP_ID_A,
            strategy=FailingStrategy(
                strategy_id=STRATEGY_ID_A,
                message="candidate-a failed",
            ),
            name="workflow-a",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_B,
            step_id=STEP_ID_B,
            strategy=FailingStrategy(
                strategy_id=STRATEGY_ID_B,
                message="candidate-b failed",
            ),
            name="workflow-b",
        ),
        create_workflow(
            workflow_id=WORKFLOW_ID_C,
            step_id=STEP_ID_C,
            strategy=FailingStrategy(
                strategy_id=STRATEGY_ID_C,
                message="candidate-c failed",
            ),
            name="workflow-c",
        ),
    )

    evaluator = RecordingEvaluator()

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
            evaluator=create_outcome_evaluator(evaluator),
        ).run(
            workflows=workflows,
            dataset=create_dataset(),
        )
    )

    assert evaluator.actual_values == []
    assert len(result.ranking.entries) == 3
    assert all(scorecard.quality_score == 0.0 for scorecard in result.scorecards)
    assert tuple(evidence.candidate_signature for evidence in result.ranked_evidence) == (
        workflows[0].signature,
        workflows[1].signature,
        workflows[2].signature,
    )


def test_experiment_runner_runs_every_candidate_for_every_case() -> None:
    """Each candidate executes once per benchmark case."""

    strategy_a = StaticStrategy(
        strategy_id=STRATEGY_ID_A,
        output="success",
        estimated_cost_usd=0.05,
    )

    strategy_b = StaticStrategy(
        strategy_id=STRATEGY_ID_B,
        output="success",
        estimated_cost_usd=0.05,
    )

    asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
        ).run(
            workflows=(
                create_workflow(
                    workflow_id=WORKFLOW_ID_A,
                    step_id=STEP_ID_A,
                    strategy=strategy_a,
                    name="workflow-a",
                ),
                create_workflow(
                    workflow_id=WORKFLOW_ID_B,
                    step_id=STEP_ID_B,
                    strategy=strategy_b,
                    name="workflow-b",
                ),
            ),
            dataset=create_multi_case_dataset(
                create_case(
                    case_id=CASE_ID_A,
                    input_value="first",
                    expected_value="success",
                ),
                create_case(
                    case_id=CASE_ID_B,
                    input_value="second",
                    expected_value="success",
                ),
                create_case(
                    case_id=CASE_ID_C,
                    input_value="third",
                    expected_value="success",
                ),
            ),
        )
    )

    assert strategy_a.calls == 3
    assert strategy_b.calls == 3


def test_experiment_runner_supplies_each_case_input_to_context() -> None:
    """Every case's input reaches its run through the workflow context."""

    strategy = EchoInputStrategy()

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
        ).run(
            workflows=(
                create_workflow(
                    workflow_id=WORKFLOW_ID_A,
                    step_id=STEP_ID_A,
                    strategy=strategy,
                    name="workflow-a",
                ),
            ),
            dataset=create_multi_case_dataset(
                create_case(
                    case_id=CASE_ID_A,
                    input_value="alpha",
                    expected_value="alpha",
                ),
                create_case(
                    case_id=CASE_ID_B,
                    input_value="beta",
                    expected_value="beta",
                ),
            ),
        )
    )

    assert strategy.inputs == [
        "alpha",
        "beta",
    ]
    assert result.winner.quality_score == pytest.approx(1.0)


def test_experiment_runner_judges_each_case_with_its_own_comparison() -> None:
    """Each case's result is judged by the evaluator for its comparison."""

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
        ).run(
            workflows=(
                create_workflow(
                    workflow_id=WORKFLOW_ID_A,
                    step_id=STEP_ID_A,
                    strategy=StaticStrategy(
                        strategy_id=STRATEGY_ID_A,
                        output="success",
                        estimated_cost_usd=0.05,
                    ),
                    name="workflow-a",
                ),
            ),
            dataset=create_multi_case_dataset(
                create_case(
                    case_id=CASE_ID_A,
                    input_value="first",
                    expected_value="SUCCESS",
                    comparison=OutcomeComparison.EXACT,
                ),
                create_case(
                    case_id=CASE_ID_B,
                    input_value="second",
                    expected_value="SUCCESS",
                    comparison=OutcomeComparison.NORMALIZED,
                ),
            ),
        )
    )

    assert result.winner.quality_score == pytest.approx(0.5)


def test_experiment_runner_combines_case_scorecards_by_mean() -> None:
    """A candidate's scorecard is the per-dimension mean of its case scorecards."""

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
        ).run(
            workflows=(
                create_workflow(
                    workflow_id=WORKFLOW_ID_A,
                    step_id=STEP_ID_A,
                    strategy=StaticStrategy(
                        strategy_id=STRATEGY_ID_A,
                        output="success",
                        estimated_cost_usd=0.05,
                    ),
                    name="workflow-a",
                ),
            ),
            dataset=create_multi_case_dataset(
                create_case(
                    case_id=CASE_ID_A,
                    input_value="first",
                    expected_value="success",
                ),
                create_case(
                    case_id=CASE_ID_B,
                    input_value="second",
                    expected_value="other",
                ),
                create_case(
                    case_id=CASE_ID_C,
                    input_value="third",
                    expected_value="other",
                ),
                create_case(
                    case_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb4"),
                    input_value="fourth",
                    expected_value="other",
                ),
            ),
        )
    )

    scorecard = result.winner

    assert scorecard.quality_score == pytest.approx(0.25)
    assert scorecard.reliability_score == pytest.approx(1.0)
    assert scorecard.latency_score == pytest.approx(1.0)
    assert scorecard.cost_score == pytest.approx(1.0)
    assert scorecard.overall_score == pytest.approx((0.25 + 1.0 + 1.0 + 1.0) / 4.0)
    assert scorecard.rationale == "Benchmark aggregate across 4 cases."


def test_experiment_runner_scores_failed_case_among_passing_cases() -> None:
    """A run that fails on one case counts as a failed case, not an abort."""

    class FailOnInputStrategy(StaticStrategy):
        """Fail only when the workflow input is the configured value."""

        async def run(
            self,
            _context: Context,
        ) -> StrategyOutcome:
            """Fail on the configured input and succeed otherwise."""

            event = _context.latest(
                WORKFLOW_INPUT_EVENT_TYPE,
            )

            if event is not None and event.payload["input"] == "explode":
                self.calls += 1

                raise RuntimeError("Provider unavailable.")

            return await super().run(_context)

    strategy = FailOnInputStrategy(
        strategy_id=STRATEGY_ID_A,
        output="success",
        estimated_cost_usd=0.05,
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=create_scorer(),
        ).run(
            workflows=(
                create_workflow(
                    workflow_id=WORKFLOW_ID_A,
                    step_id=STEP_ID_A,
                    strategy=strategy,
                    name="workflow-a",
                ),
            ),
            dataset=create_multi_case_dataset(
                create_case(
                    case_id=CASE_ID_A,
                    input_value="fine",
                    expected_value="success",
                ),
                create_case(
                    case_id=CASE_ID_B,
                    input_value="explode",
                    expected_value="success",
                ),
            ),
        )
    )

    assert strategy.calls == 2
    assert result.winner.quality_score == pytest.approx(0.5)


def test_experiment_runner_rejects_empty_dataset_before_execution() -> None:
    """A benchmark without cases is rejected before any candidate executes."""

    strategy = StaticStrategy(
        strategy_id=STRATEGY_ID_A,
        output="success",
        estimated_cost_usd=0.05,
    )

    dataset = create_multi_case_dataset()

    with pytest.raises(
        ValueError,
    ) as error:
        asyncio.run(
            WorkflowExperimentRunner(
                scorer=create_scorer(),
            ).run(
                workflows=(
                    create_workflow(
                        workflow_id=WORKFLOW_ID_A,
                        step_id=STEP_ID_A,
                        strategy=strategy,
                        name="workflow-a",
                    ),
                ),
                dataset=dataset,
            )
        )

    assert str(error.value) == f"Benchmark {DATASET_ID} has no cases."
    assert strategy.calls == 0


def test_experiment_runner_rejects_unsupported_comparison_before_execution() -> None:
    """A benchmark with an unsupported comparison never partially runs."""

    strategy = StaticStrategy(
        strategy_id=STRATEGY_ID_A,
        output="success",
        estimated_cost_usd=0.05,
    )

    with pytest.raises(
        UnsupportedComparisonError,
    ) as error:
        asyncio.run(
            WorkflowExperimentRunner(
                scorer=create_scorer(),
            ).run(
                workflows=(
                    create_workflow(
                        workflow_id=WORKFLOW_ID_A,
                        step_id=STEP_ID_A,
                        strategy=strategy,
                        name="workflow-a",
                    ),
                ),
                dataset=create_multi_case_dataset(
                    create_case(
                        case_id=CASE_ID_A,
                        input_value="first",
                        expected_value="success",
                    ),
                    create_case(
                        case_id=CASE_ID_B,
                        input_value="second",
                        expected_value="success",
                        comparison=OutcomeComparison.SEMANTIC,
                    ),
                ),
            )
        )

    assert str(error.value) == (
        f"Benchmark case {CASE_ID_B} uses comparison 'semantic', which is not supported yet."
    )
    assert strategy.calls == 0

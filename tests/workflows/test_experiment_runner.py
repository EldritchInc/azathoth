"""Tests for workflow experiment orchestration."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    EvaluationResult,
    EvaluationStatus,
    EvaluatorMetadata,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.strategies import (
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowExperimentResult,
    WorkflowExperimentRunner,
    WorkflowMetadata,
    WorkflowScorer,
    WorkflowScoringPolicy,
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
    strategy: StaticStrategy,
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
            ),
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
        ).run(
            workflows=workflows,
            context=Context(),
            evaluator=RecordingEvaluator(),
            expected_outcome=create_expected_outcome(),
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
        ).run(
            workflows=workflows,
            context=Context(),
            evaluator=evaluator,
            expected_outcome=create_expected_outcome(),
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
        ).run(
            workflows=workflows,
            context=Context(),
            evaluator=RecordingEvaluator(),
            expected_outcome=create_expected_outcome(),
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
        ).run(
            workflows=workflows,
            context=Context(),
            evaluator=RecordingEvaluator(),
            expected_outcome=create_expected_outcome(),
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
        ).run(
            workflows=workflows,
            context=Context(),
            evaluator=RecordingEvaluator(),
            expected_outcome=create_expected_outcome(),
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
        ).run(
            workflows=workflows,
            context=Context(),
            evaluator=RecordingEvaluator(),
            expected_outcome=create_expected_outcome(),
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
        ).run(
            workflows=workflows,
            context=Context(),
            evaluator=RecordingEvaluator(),
            expected_outcome=create_expected_outcome(),
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
            ).run(
                workflows=(),
                context=Context(),
                evaluator=RecordingEvaluator(),
                expected_outcome=create_expected_outcome(),
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
        ).run(
            workflows=workflows,
            context=Context(),
            evaluator=RecordingEvaluator(),
            expected_outcome=create_expected_outcome(),
        )
    )

    restored = WorkflowExperimentResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.winner == result.winner

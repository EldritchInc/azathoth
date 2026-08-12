"""Tests for workflow experiment orchestration."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    ExactMatchEvaluator,
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
    WorkflowExperimentRunner,
    WorkflowMetadata,
    WorkflowScorer,
    WorkflowScoringPolicy,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


class DeterministicStrategy:
    """Return a deterministic workflow experiment result."""

    def __init__(self) -> None:
        self._metadata = StrategyMetadata(
            id=STRATEGY_ID,
            name="deterministic-strategy",
            description="Return a deterministic experiment result.",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return self._metadata

    async def run(
        self,
        _context: Context,
    ) -> StrategyOutcome:
        """Return a deterministic successful outcome."""

        return StrategyOutcome(
            output="success",
            metrics=StrategyExecutionMetrics(
                provider="test-provider",
                model="test-model",
                prompt_tokens=10,
                completion_tokens=1,
                total_tokens=11,
                latency_ms=100,
                estimated_cost_usd=0.01,
            ),
        )


def create_candidate() -> WorkflowCandidate:
    """Create a deterministic workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="experiment-workflow",
            description="Workflow used for experiment runner tests.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ID,
                strategy=DeterministicStrategy(),
            ),
        ),
    )


def test_experiment_runner_returns_experiment_result() -> None:
    """Experiment runner should execute, evaluate, score, and rank."""

    runner = WorkflowExperimentRunner(
        scorer=WorkflowScorer(
            policy=WorkflowScoringPolicy(
                target_latency_seconds=10.0,
                target_cost_usd=0.10,
            ),
        ),
    )

    result = asyncio.run(
        runner.run(
            workflows=(create_candidate(),),
            context=Context(),
            evaluator=ExactMatchEvaluator(),
            expected_outcome=ExpectedOutcome(
                description="Workflow should return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
        )
    )

    assert len(result.scorecards) == 1

    assert result.winner == result.scorecards[0]

    assert result.winner.quality_score == pytest.approx(1.0)

    assert result.winner.reliability_score == pytest.approx(1.0)

    assert result.winner.latency_score == pytest.approx(1.0)

    assert result.winner.cost_score == pytest.approx(1.0)

    assert result.winner.overall_score == pytest.approx(1.0)

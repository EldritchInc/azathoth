"""Tests for replay workflow optimization."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.optimization import (
    ReplayWorkflowOptimizer,
    WorkflowOptimizationResult,
)
from azathoth.strategies import (
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    RankedWorkflow,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
    WorkflowMetadata,
    WorkflowRanking,
    WorkflowScorecard,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")
STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")
SECOND_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")


class StaticStrategy:
    """Return one deterministic strategy outcome."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=f"strategy-{strategy_id}",
            description="Deterministic replay optimization strategy.",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return self._metadata

    async def run(
        self,
        _context: Context,
    ) -> StrategyOutcome:
        """Return a deterministic strategy outcome."""

        return StrategyOutcome(
            output="success",
        )


def create_candidate(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy_id: UUID,
) -> WorkflowCandidate:
    """Create a deterministic workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=f"workflow-{workflow_id}",
            description="Replay workflow optimization candidate.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=step_id,
                strategy=StaticStrategy(
                    strategy_id=strategy_id,
                ),
            ),
        ),
    )


def create_candidates() -> tuple[WorkflowCandidate, ...]:
    """Create a deterministic candidate population."""

    return (
        create_candidate(
            workflow_id=WORKFLOW_ID,
            step_id=STEP_ID,
            strategy_id=STRATEGY_ID,
        ),
        create_candidate(
            workflow_id=SECOND_WORKFLOW_ID,
            step_id=SECOND_STEP_ID,
            strategy_id=SECOND_STRATEGY_ID,
        ),
    )


def create_scorecard(
    *,
    overall_score: float,
) -> WorkflowScorecard:
    """Create a deterministic workflow scorecard."""

    return WorkflowScorecard(
        quality_score=overall_score,
        reliability_score=overall_score,
        latency_score=overall_score,
        cost_score=overall_score,
        overall_score=overall_score,
    )


def create_experiment() -> WorkflowExperimentResult:
    """Create a deterministic workflow experiment result."""

    winner = create_scorecard(
        overall_score=0.9,
    )
    runner_up = create_scorecard(
        overall_score=0.7,
    )

    candidates = create_candidates()

    return WorkflowExperimentResult(
        evidence=(
            WorkflowExperimentEvidence(
                candidate_signature=candidates[0].signature,
                scorecard=winner,
            ),
            WorkflowExperimentEvidence(
                candidate_signature=candidates[1].signature,
                scorecard=runner_up,
            ),
        ),
        ranking=WorkflowRanking(
            entries=(
                RankedWorkflow(
                    rank=1,
                    scorecard=winner,
                ),
                RankedWorkflow(
                    rank=2,
                    scorecard=runner_up,
                ),
            ),
        ),
    )


def test_replay_optimizer_returns_optimization_result() -> None:
    """Replay optimization should produce a workflow optimization result."""

    result = ReplayWorkflowOptimizer().optimize(
        experiment=create_experiment(),
        candidates=create_candidates(),
        generation=1,
    )

    assert isinstance(
        result,
        WorkflowOptimizationResult,
    )


def test_replay_optimizer_records_generation() -> None:
    """Replay optimization should preserve the requested generation."""

    result = ReplayWorkflowOptimizer().optimize(
        experiment=create_experiment(),
        candidates=create_candidates(),
        generation=2,
    )

    assert result.generation == 2


def test_replay_optimizer_preserves_previous_experiment() -> None:
    """Replay optimization should preserve experiment evidence."""

    experiment = create_experiment()

    result = ReplayWorkflowOptimizer().optimize(
        experiment=experiment,
        candidates=create_candidates(),
        generation=1,
    )

    assert result.previous_experiment == experiment


def test_replay_optimizer_preserves_candidates() -> None:
    """Replay optimization should return the supplied candidate population."""

    candidates = create_candidates()

    result = ReplayWorkflowOptimizer().optimize(
        experiment=create_experiment(),
        candidates=candidates,
        generation=1,
    )

    assert result.candidates == candidates


def test_replay_optimizer_preserves_candidate_order() -> None:
    """Replay optimization should preserve candidate population order."""

    candidates = create_candidates()

    result = ReplayWorkflowOptimizer().optimize(
        experiment=create_experiment(),
        candidates=candidates,
        generation=1,
    )

    assert tuple(candidate.metadata.id for candidate in result.candidates) == (
        WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
    )


def test_replay_optimizer_preserves_candidate_instances() -> None:
    """Replay optimization should not replace executable candidate objects."""

    candidates = create_candidates()

    result = ReplayWorkflowOptimizer().optimize(
        experiment=create_experiment(),
        candidates=candidates,
        generation=1,
    )

    assert result.candidates[0] is candidates[0]
    assert result.candidates[1] is candidates[1]


def test_replay_optimizer_supports_subsequent_generations() -> None:
    """Replay optimization should support generations beyond the first."""

    candidates = create_candidates()
    experiment = create_experiment()
    optimizer = ReplayWorkflowOptimizer()

    first = optimizer.optimize(
        experiment=experiment,
        candidates=candidates,
        generation=1,
    )

    second = optimizer.optimize(
        experiment=experiment,
        candidates=first.candidates,
        generation=2,
    )

    assert first.generation == 1
    assert second.generation == 2
    assert second.candidates == candidates


def test_replay_optimizer_is_deterministic() -> None:
    """Repeated optimization should produce equivalent results."""

    candidates = create_candidates()
    experiment = create_experiment()
    optimizer = ReplayWorkflowOptimizer()

    first = optimizer.optimize(
        experiment=experiment,
        candidates=candidates,
        generation=3,
    )

    second = optimizer.optimize(
        experiment=experiment,
        candidates=candidates,
        generation=3,
    )

    assert first.generation == second.generation
    assert first.previous_experiment == second.previous_experiment
    assert first.candidates == second.candidates


def test_replay_optimizer_does_not_depend_on_experiment_winner() -> None:
    """Replay optimization should preserve all candidates regardless of ranking."""

    candidates = create_candidates()

    result = ReplayWorkflowOptimizer().optimize(
        experiment=create_experiment(),
        candidates=candidates,
        generation=1,
    )

    assert len(result.candidates) == 2
    assert result.candidates == candidates


def test_replay_optimizer_rejects_zero_generation() -> None:
    """Replay optimization should preserve result generation validation."""

    with pytest.raises(
        ValidationError,
    ):
        ReplayWorkflowOptimizer().optimize(
            experiment=create_experiment(),
            candidates=create_candidates(),
            generation=0,
        )


def test_replay_optimizer_rejects_negative_generation() -> None:
    """Replay optimization should reject negative generations."""

    with pytest.raises(
        ValidationError,
    ):
        ReplayWorkflowOptimizer().optimize(
            experiment=create_experiment(),
            candidates=create_candidates(),
            generation=-1,
        )


def test_replay_optimizer_rejects_empty_candidate_population() -> None:
    """Replay optimization should reject an empty next generation."""

    with pytest.raises(
        ValidationError,
    ):
        ReplayWorkflowOptimizer().optimize(
            experiment=create_experiment(),
            candidates=(),
            generation=1,
        )

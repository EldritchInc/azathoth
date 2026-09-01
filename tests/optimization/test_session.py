"""Tests for workflow optimization sessions."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.optimization import (
    WorkflowOptimizationResult,
    WorkflowOptimizationSession,
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
            description="Deterministic session test strategy.",
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
            description="Workflow optimization session candidate.",
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
    """Create a deterministic initial candidate population."""

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


def create_generation(
    *,
    generation: int,
    candidates: tuple[WorkflowCandidate, ...],
) -> WorkflowOptimizationResult:
    """Create a deterministic workflow optimization generation."""

    return WorkflowOptimizationResult(
        generation=generation,
        previous_experiment=create_experiment(),
        candidates=candidates,
    )


def create_session() -> WorkflowOptimizationSession:
    """Create a deterministic workflow optimization session."""

    candidates = create_candidates()

    return WorkflowOptimizationSession(
        initial_candidates=candidates,
        generations=(
            create_generation(
                generation=1,
                candidates=candidates,
            ),
            create_generation(
                generation=2,
                candidates=candidates,
            ),
        ),
    )


def test_session_records_initial_candidates() -> None:
    session = create_session()

    assert tuple(candidate.metadata.id for candidate in session.initial_candidates) == (
        WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
    )


def test_session_records_generations() -> None:
    session = create_session()

    assert tuple(generation.generation for generation in session.generations) == (
        1,
        2,
    )


def test_session_allows_no_completed_generations() -> None:
    session = WorkflowOptimizationSession(
        initial_candidates=create_candidates(),
    )

    assert session.generations == ()


def test_session_rejects_empty_initial_candidates() -> None:
    with pytest.raises(
        ValidationError,
    ):
        WorkflowOptimizationSession(
            initial_candidates=(),
        )


def test_session_rejects_generation_sequence_not_starting_at_one() -> None:
    candidates = create_candidates()

    with pytest.raises(
        ValidationError,
        match="Workflow optimization generations must be consecutive starting at 1.",
    ):
        WorkflowOptimizationSession(
            initial_candidates=candidates,
            generations=(
                create_generation(
                    generation=2,
                    candidates=candidates,
                ),
            ),
        )


def test_session_rejects_nonconsecutive_generations() -> None:
    candidates = create_candidates()

    with pytest.raises(
        ValidationError,
        match="Workflow optimization generations must be consecutive starting at 1.",
    ):
        WorkflowOptimizationSession(
            initial_candidates=candidates,
            generations=(
                create_generation(
                    generation=1,
                    candidates=candidates,
                ),
                create_generation(
                    generation=3,
                    candidates=candidates,
                ),
            ),
        )


def test_session_is_immutable() -> None:
    session = create_session()

    with pytest.raises(
        ValidationError,
    ):
        session.generations = ()

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
PROPOSED_WORKFLOW_ID = UUID("77777777-7777-7777-7777-777777777777")
PROPOSED_STEP_ID = UUID("88888888-8888-8888-8888-888888888888")
PROPOSED_STRATEGY_ID = UUID("99999999-9999-9999-9999-999999999999")


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


def create_proposed_candidate() -> WorkflowCandidate:
    """Create a candidate the initial population does not contain."""

    return create_candidate(
        workflow_id=PROPOSED_WORKFLOW_ID,
        step_id=PROPOSED_STEP_ID,
        strategy_id=PROPOSED_STRATEGY_ID,
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


def create_experiment(
    candidates: tuple[WorkflowCandidate, ...] | None = None,
    *,
    winner_index: int = 0,
) -> WorkflowExperimentResult:
    """Create a deterministic experiment over a population.

    The candidate at `winner_index` scores highest; the others rank after it
    in population order. The default population is the initial one.
    """

    population = create_candidates() if candidates is None else candidates

    scores = [0.7 - 0.1 * index for index in range(len(population))]
    scores.insert(winner_index, 0.9)
    scores.pop()

    scorecards = tuple(create_scorecard(overall_score=score) for score in scores)

    ranked = sorted(
        scorecards,
        key=lambda scorecard: scorecard.overall_score,
        reverse=True,
    )

    return WorkflowExperimentResult(
        evidence=tuple(
            WorkflowExperimentEvidence(
                candidate_signature=candidate.signature,
                scorecard=scorecard,
            )
            for candidate, scorecard in zip(population, scorecards, strict=True)
        ),
        ranking=WorkflowRanking(
            entries=tuple(
                RankedWorkflow(
                    rank=rank,
                    scorecard=scorecard,
                )
                for rank, scorecard in enumerate(ranked, start=1)
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


def create_session_with_final_experiment() -> WorkflowOptimizationSession:
    """Create a one-generation session whose proposal won its final evaluation."""

    candidates = create_candidates()
    proposed = (*candidates, create_proposed_candidate())

    return WorkflowOptimizationSession(
        initial_candidates=candidates,
        generations=(
            create_generation(
                generation=1,
                candidates=proposed,
            ),
        ),
        final_experiment=create_experiment(
            proposed,
            winner_index=2,
        ),
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


def test_session_has_no_final_experiment_by_default() -> None:
    assert create_session().final_experiment is None


def test_session_records_a_final_experiment() -> None:
    session = create_session_with_final_experiment()

    assert session.final_experiment is not None
    assert len(session.final_experiment.evidence) == 3


def test_final_population_is_the_last_generations_candidates() -> None:
    session = create_session_with_final_experiment()

    assert tuple(candidate.metadata.id for candidate in session.final_population) == (
        WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
        PROPOSED_WORKFLOW_ID,
    )


def test_final_population_is_the_initial_population_before_any_generation() -> None:
    session = WorkflowOptimizationSession(
        initial_candidates=create_candidates(),
    )

    assert session.final_population == session.initial_candidates


def test_final_experiment_is_the_winning_experiment() -> None:
    session = create_session_with_final_experiment()

    assert session.winning_experiment == session.final_experiment
    assert session.winning_population == session.final_population


def test_final_experiment_winner_is_the_session_winner() -> None:
    session = create_session_with_final_experiment()

    assert session.winner is not None
    assert session.winner.metadata.id == PROPOSED_WORKFLOW_ID


def test_last_generation_wins_without_a_final_experiment() -> None:
    session = create_session()

    assert session.winning_experiment == session.generations[-1].previous_experiment
    assert session.winning_population == session.generations[0].candidates
    assert session.winner is not None
    assert session.winner.metadata.id == WORKFLOW_ID


def test_one_generation_without_a_final_experiment_wins_from_the_initial_population() -> None:
    candidates = create_candidates()

    session = WorkflowOptimizationSession(
        initial_candidates=candidates,
        generations=(
            create_generation(
                generation=1,
                candidates=candidates,
            ),
        ),
    )

    assert session.winning_population == candidates
    assert session.winner is not None
    assert session.winner.metadata.id == WORKFLOW_ID


def test_session_without_generations_has_no_winner() -> None:
    session = WorkflowOptimizationSession(
        initial_candidates=create_candidates(),
    )

    assert session.winning_experiment is None
    assert session.winning_population == ()
    assert session.winner is None


def test_session_rejects_a_final_experiment_without_generations() -> None:
    with pytest.raises(
        ValidationError,
        match="A workflow optimization final evaluation requires at least one generation.",
    ):
        WorkflowOptimizationSession(
            initial_candidates=create_candidates(),
            final_experiment=create_experiment(),
        )


def test_session_rejects_a_final_experiment_missing_a_proposal() -> None:
    candidates = create_candidates()

    with pytest.raises(
        ValidationError,
        match="must evaluate exactly the last generation's candidates",
    ):
        WorkflowOptimizationSession(
            initial_candidates=candidates,
            generations=(
                create_generation(
                    generation=1,
                    candidates=(*candidates, create_proposed_candidate()),
                ),
            ),
            final_experiment=create_experiment(candidates),
        )


def test_session_rejects_a_final_experiment_over_another_population() -> None:
    candidates = create_candidates()

    with pytest.raises(
        ValidationError,
        match="must evaluate exactly the last generation's candidates",
    ):
        WorkflowOptimizationSession(
            initial_candidates=candidates,
            generations=(
                create_generation(
                    generation=1,
                    candidates=candidates,
                ),
            ),
            final_experiment=create_experiment(
                (candidates[0], create_proposed_candidate()),
            ),
        )

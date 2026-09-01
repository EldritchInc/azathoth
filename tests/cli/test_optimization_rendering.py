"""Tests for human-readable workflow optimization rendering."""

from uuid import UUID

from azathoth.cli import render_workflow_optimization_session
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

INITIAL_STRATEGY_ID = UUID("22222222-2222-2222-2222-222222222222")

OPTIMIZED_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")


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
            description="Deterministic rendering strategy.",
        )

    @property
    def metadata(
        self,
    ) -> StrategyMetadata:
        """Return deterministic strategy metadata."""

        return self._metadata

    async def run(
        self,
        _context: Context,
    ) -> StrategyOutcome:
        """Return deterministic strategy output."""

        return StrategyOutcome(
            output="success",
        )


def create_candidate(
    *,
    strategy_id: UUID,
) -> WorkflowCandidate:
    """Create one deterministic executable workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="optimization-rendering",
            description="Render an optimization session.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ID,
                strategy=StaticStrategy(
                    strategy_id=strategy_id,
                ),
            ),
        ),
    )


def create_scorecard(
    *,
    quality: float,
    reliability: float,
    latency: float,
    cost: float,
    overall: float,
) -> WorkflowScorecard:
    """Create deterministic workflow scoring evidence."""

    return WorkflowScorecard(
        quality_score=quality,
        reliability_score=reliability,
        latency_score=latency,
        cost_score=cost,
        overall_score=overall,
        rationale="Deterministic rendering score.",
    )


def create_experiment(
    *,
    candidates: tuple[WorkflowCandidate, ...],
    scorecards: tuple[WorkflowScorecard, ...],
    winner_index: int,
) -> WorkflowExperimentResult:
    """Create deterministic candidate-associated experiment evidence."""

    evidence = tuple(
        WorkflowExperimentEvidence(
            candidate_signature=candidate.signature,
            scorecard=scorecard,
        )
        for candidate, scorecard in zip(
            candidates,
            scorecards,
            strict=True,
        )
    )

    winner = scorecards[winner_index]

    remaining = tuple(
        scorecard for index, scorecard in enumerate(scorecards) if index != winner_index
    )

    return WorkflowExperimentResult(
        evidence=evidence,
        ranking=WorkflowRanking(
            entries=tuple(
                RankedWorkflow(
                    rank=rank,
                    scorecard=scorecard,
                )
                for rank, scorecard in enumerate(
                    (
                        winner,
                        *remaining,
                    ),
                    start=1,
                )
            ),
        ),
    )


def create_session() -> WorkflowOptimizationSession:
    """Create a deterministic two-generation optimization session."""

    initial = create_candidate(
        strategy_id=INITIAL_STRATEGY_ID,
    )

    optimized = create_candidate(
        strategy_id=OPTIMIZED_STRATEGY_ID,
    )

    initial_scorecard = create_scorecard(
        quality=1.0,
        reliability=1.0,
        latency=0.8,
        cost=0.1,
        overall=0.725,
    )

    optimized_scorecard = create_scorecard(
        quality=1.0,
        reliability=1.0,
        latency=0.9,
        cost=1.0,
        overall=0.975,
    )

    retained_scorecard = create_scorecard(
        quality=1.0,
        reliability=1.0,
        latency=0.8,
        cost=0.1,
        overall=0.725,
    )

    return WorkflowOptimizationSession(
        initial_candidates=(initial,),
        generations=(
            WorkflowOptimizationResult(
                generation=1,
                previous_experiment=create_experiment(
                    candidates=(initial,),
                    scorecards=(initial_scorecard,),
                    winner_index=0,
                ),
                candidates=(
                    initial,
                    optimized,
                ),
            ),
            WorkflowOptimizationResult(
                generation=2,
                previous_experiment=create_experiment(
                    candidates=(
                        initial,
                        optimized,
                    ),
                    scorecards=(
                        retained_scorecard,
                        optimized_scorecard,
                    ),
                    winner_index=1,
                ),
                candidates=(
                    initial,
                    optimized,
                ),
            ),
        ),
    )


def test_render_workflow_optimization_session_renders_summary() -> None:
    rendered = render_workflow_optimization_session(
        create_session(),
    )

    assert rendered.startswith(
        "Workflow: optimization-rendering\n"
        f"Workflow ID: {WORKFLOW_ID}\n"
        "Initial Candidates: 1\n"
        "Generations: 2"
    )


def test_render_workflow_optimization_session_renders_generations() -> None:
    rendered = render_workflow_optimization_session(
        create_session(),
    )

    assert "Generation 1\n" in rendered
    assert "Generation 2\n" in rendered

    assert "Evaluated Candidates: 1\n" in rendered
    assert "Evaluated Candidates: 2\n" in rendered

    assert "Next Population: 2" in rendered


def test_render_workflow_optimization_session_renders_empirical_winners() -> None:
    rendered = render_workflow_optimization_session(
        create_session(),
    )

    assert f"  Strategy IDs: {INITIAL_STRATEGY_ID}" in rendered

    assert f"  Strategy IDs: {OPTIMIZED_STRATEGY_ID}" in rendered


def test_render_workflow_optimization_session_renders_winner_scores() -> None:
    rendered = render_workflow_optimization_session(
        create_session(),
    )

    assert "  Quality: 1.000000" in rendered
    assert "  Reliability: 1.000000" in rendered
    assert "  Latency: 0.900000" in rendered
    assert "  Cost: 1.000000" in rendered
    assert "  Overall: 0.975000" in rendered


def test_render_workflow_optimization_session_preserves_generation_order() -> None:
    rendered = render_workflow_optimization_session(
        create_session(),
    )

    assert rendered.index("Generation 1") < rendered.index("Generation 2")


def test_render_workflow_optimization_session_does_not_claim_proposals_improved() -> None:
    rendered = render_workflow_optimization_session(
        create_session(),
    )

    assert "improved" not in rendered.lower()
    assert "better" not in rendered.lower()

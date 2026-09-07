"""Tests for human-readable workflow optimization rendering."""

from uuid import UUID

from azathoth.cli import render_workflow_optimization_session
from azathoth.context import Context
from azathoth.optimization import (
    WorkflowOptimizationResult,
    WorkflowOptimizationSession,
)
from azathoth.prompting import (
    ModelBinding,
    PromptStrategy,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    Prompt,
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

MODEL_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")

STATIC_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")

MODEL_STEP_ID = UUID("77777777-7777-7777-7777-777777777777")

STATIC_STEP_ID = UUID("88888888-8888-8888-8888-888888888888")

MODEL_IDENTIFIER = "openrouter/example-winner"


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


def create_heterogeneous_candidate() -> WorkflowCandidate:
    """Create one winner containing model-backed and non-model steps."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="heterogeneous-optimization-rendering",
            description="Render heterogeneous winner bindings.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=MODEL_STEP_ID,
                strategy=PromptStrategy(
                    metadata=StrategyMetadata(
                        id=MODEL_STRATEGY_ID,
                        name="classify request",
                        description="Classify with the empirically selected model.",
                    ),
                    prompt=Prompt(
                        text="Return the classification.",
                    ),
                    language_model=DeterministicLanguageModel(
                        provider="openrouter",
                        model="example-winner",
                        response_text="positive",
                    ),
                    model_binding=ModelBinding(
                        identifier=MODEL_IDENTIFIER,
                    ),
                ),
            ),
            WorkflowCandidateStep(
                id=STATIC_STEP_ID,
                strategy=StaticStrategy(
                    strategy_id=STATIC_STRATEGY_ID,
                ),
                depends_on=(MODEL_STEP_ID,),
            ),
        ),
    )


def create_heterogeneous_session() -> WorkflowOptimizationSession:
    """Create one optimization session with a heterogeneous winner."""

    winner = create_heterogeneous_candidate()

    scorecard = create_scorecard(
        quality=1.0,
        reliability=1.0,
        latency=0.9,
        cost=1.0,
        overall=0.975,
    )

    return WorkflowOptimizationSession(
        initial_candidates=(winner,),
        generations=(
            WorkflowOptimizationResult(
                generation=1,
                previous_experiment=create_experiment(
                    candidates=(winner,),
                    scorecards=(scorecard,),
                    winner_index=0,
                ),
                candidates=(winner,),
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


def test_render_workflow_optimization_session_renders_winner_steps() -> None:
    rendered = render_workflow_optimization_session(
        create_heterogeneous_session(),
    )

    assert "Winner:" in rendered

    assert "  Step: classify request" in rendered
    assert f"  Step ID: {MODEL_STEP_ID}" in rendered
    assert f"  Strategy ID: {MODEL_STRATEGY_ID}" in rendered

    assert f"  Step: strategy-{STATIC_STRATEGY_ID}" in rendered
    assert f"  Step ID: {STATIC_STEP_ID}" in rendered
    assert f"  Strategy ID: {STATIC_STRATEGY_ID}" in rendered


def test_render_workflow_optimization_session_renders_winner_model_bindings() -> None:
    rendered = render_workflow_optimization_session(
        create_heterogeneous_session(),
    )

    assert f"  Model: {MODEL_IDENTIFIER}" in rendered


def test_render_workflow_optimization_session_only_renders_actual_model_bindings() -> None:
    rendered = render_workflow_optimization_session(
        create_heterogeneous_session(),
    )

    assert rendered.count("  Model:") == 1

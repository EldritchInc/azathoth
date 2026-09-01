"""Tests for resolving workflow experiment evidence to executable candidates."""

from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.optimization import (
    resolve_workflow_candidate,
    resolve_workflow_experiment_evidence,
    resolve_workflow_experiment_winner,
)
from azathoth.strategies import (
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    RankedWorkflow,
    WorkflowCandidate,
    WorkflowCandidateSignature,
    WorkflowCandidateStep,
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
    WorkflowMetadata,
    WorkflowRanking,
    WorkflowScorecard,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
UNKNOWN_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")
SECOND_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

FIRST_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")
SECOND_STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")
UNKNOWN_STRATEGY_ID = UUID("88888888-8888-8888-8888-888888888888")


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
            description="Deterministic candidate resolution strategy.",
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
    workflow_id: UUID,
    step_id: UUID,
    strategy_id: UUID,
) -> WorkflowCandidate:
    """Create one deterministic executable workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=f"workflow-{workflow_id}",
            description="Workflow candidate resolution test candidate.",
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
    """Create a deterministic executable candidate population."""

    return (
        create_candidate(
            workflow_id=FIRST_WORKFLOW_ID,
            step_id=FIRST_STEP_ID,
            strategy_id=FIRST_STRATEGY_ID,
        ),
        create_candidate(
            workflow_id=SECOND_WORKFLOW_ID,
            step_id=SECOND_STEP_ID,
            strategy_id=SECOND_STRATEGY_ID,
        ),
    )


def create_scorecard(
    score: float,
) -> WorkflowScorecard:
    """Create deterministic experiment scoring evidence."""

    return WorkflowScorecard(
        quality_score=score,
        reliability_score=score,
        latency_score=score,
        cost_score=score,
        overall_score=score,
    )


def create_experiment(
    candidates: tuple[WorkflowCandidate, ...],
) -> WorkflowExperimentResult:
    """Create an experiment whose second candidate is the winner."""

    first_scorecard = create_scorecard(0.7)
    second_scorecard = create_scorecard(0.9)

    return WorkflowExperimentResult(
        evidence=(
            WorkflowExperimentEvidence(
                candidate_signature=candidates[0].signature,
                scorecard=first_scorecard,
            ),
            WorkflowExperimentEvidence(
                candidate_signature=candidates[1].signature,
                scorecard=second_scorecard,
            ),
        ),
        ranking=WorkflowRanking(
            entries=(
                RankedWorkflow(
                    rank=1,
                    scorecard=second_scorecard,
                ),
                RankedWorkflow(
                    rank=2,
                    scorecard=first_scorecard,
                ),
            ),
        ),
    )


def test_resolve_workflow_candidate_returns_matching_candidate() -> None:
    candidates = create_candidates()

    resolved = resolve_workflow_candidate(
        signature=candidates[1].signature,
        candidates=candidates,
    )

    assert resolved is candidates[1]


def test_resolve_workflow_candidate_is_independent_of_population_order() -> None:
    candidates = create_candidates()

    resolved = resolve_workflow_candidate(
        signature=candidates[0].signature,
        candidates=tuple(reversed(candidates)),
    )

    assert resolved is candidates[0]


def test_resolve_workflow_candidate_rejects_missing_candidate() -> None:
    candidates = create_candidates()

    with pytest.raises(
        ValueError,
        match="does not match any supplied workflow candidate",
    ):
        resolve_workflow_candidate(
            signature=WorkflowCandidateSignature(
                workflow_id=UNKNOWN_WORKFLOW_ID,
                strategy_ids=(UNKNOWN_STRATEGY_ID,),
            ),
            candidates=candidates,
        )


def test_resolve_workflow_candidate_rejects_ambiguous_candidate() -> None:
    candidate = create_candidate(
        workflow_id=FIRST_WORKFLOW_ID,
        step_id=FIRST_STEP_ID,
        strategy_id=FIRST_STRATEGY_ID,
    )

    duplicate = create_candidate(
        workflow_id=FIRST_WORKFLOW_ID,
        step_id=SECOND_STEP_ID,
        strategy_id=FIRST_STRATEGY_ID,
    )

    assert candidate.signature == duplicate.signature

    with pytest.raises(
        ValueError,
        match="matches multiple supplied workflow candidates",
    ):
        resolve_workflow_candidate(
            signature=candidate.signature,
            candidates=(
                candidate,
                duplicate,
            ),
        )


def test_resolve_workflow_experiment_evidence_returns_matching_candidate() -> None:
    candidates = create_candidates()
    experiment = create_experiment(candidates)

    resolved = resolve_workflow_experiment_evidence(
        evidence=experiment.evidence[0],
        candidates=candidates,
    )

    assert resolved is candidates[0]


def test_resolve_workflow_experiment_winner_returns_empirical_winner() -> None:
    candidates = create_candidates()
    experiment = create_experiment(candidates)

    resolved = resolve_workflow_experiment_winner(
        experiment=experiment,
        candidates=candidates,
    )

    assert resolved is candidates[1]


def test_resolve_workflow_experiment_winner_does_not_use_candidate_position() -> None:
    candidates = create_candidates()
    experiment = create_experiment(candidates)

    reversed_candidates = tuple(reversed(candidates))

    resolved = resolve_workflow_experiment_winner(
        experiment=experiment,
        candidates=reversed_candidates,
    )

    assert resolved is candidates[1]


def test_resolve_workflow_experiment_winner_rejects_stale_population() -> None:
    candidates = create_candidates()
    experiment = create_experiment(candidates)

    with pytest.raises(
        ValueError,
        match="does not match any supplied workflow candidate",
    ):
        resolve_workflow_experiment_winner(
            experiment=experiment,
            candidates=(candidates[0],),
        )


def test_resolve_workflow_experiment_winner_preserves_exact_tie_order() -> None:
    candidates = create_candidates()
    tied_scorecard = create_scorecard(0.9)

    experiment = WorkflowExperimentResult(
        evidence=(
            WorkflowExperimentEvidence(
                candidate_signature=candidates[0].signature,
                scorecard=tied_scorecard,
            ),
            WorkflowExperimentEvidence(
                candidate_signature=candidates[1].signature,
                scorecard=tied_scorecard,
            ),
        ),
        ranking=WorkflowRanking(
            entries=(
                RankedWorkflow(
                    rank=1,
                    scorecard=tied_scorecard,
                ),
                RankedWorkflow(
                    rank=2,
                    scorecard=tied_scorecard,
                ),
            ),
        ),
    )

    resolved = resolve_workflow_experiment_winner(
        experiment=experiment,
        candidates=tuple(reversed(candidates)),
    )

    assert resolved is candidates[0]

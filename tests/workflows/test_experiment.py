"""Tests for workflow experiment results."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    RankedWorkflow,
    WorkflowCandidateSignature,
    WorkflowExperimentEvidence,
    WorkflowExperimentResult,
    WorkflowRanking,
    WorkflowScorecard,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_scorecard(
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


def create_signature(
    *,
    workflow_id: UUID,
    strategy_id: UUID,
) -> WorkflowCandidateSignature:
    """Create deterministic executable candidate identity."""

    return WorkflowCandidateSignature(
        workflow_id=workflow_id,
        strategy_ids=(strategy_id,),
    )


def create_experiment() -> WorkflowExperimentResult:
    """Create a deterministic workflow experiment."""

    winner = create_scorecard(
        0.9,
    )

    runner_up = create_scorecard(
        0.7,
    )

    return WorkflowExperimentResult(
        evidence=(
            WorkflowExperimentEvidence(
                candidate_signature=create_signature(
                    workflow_id=FIRST_WORKFLOW_ID,
                    strategy_id=FIRST_STRATEGY_ID,
                ),
                scorecard=winner,
            ),
            WorkflowExperimentEvidence(
                candidate_signature=create_signature(
                    workflow_id=SECOND_WORKFLOW_ID,
                    strategy_id=SECOND_STRATEGY_ID,
                ),
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


def test_experiment_records_candidate_evidence() -> None:
    experiment = create_experiment()

    assert experiment.evidence[0].candidate_signature == WorkflowCandidateSignature(
        workflow_id=FIRST_WORKFLOW_ID,
        strategy_ids=(FIRST_STRATEGY_ID,),
    )

    assert experiment.evidence[1].candidate_signature == WorkflowCandidateSignature(
        workflow_id=SECOND_WORKFLOW_ID,
        strategy_ids=(SECOND_STRATEGY_ID,),
    )


def test_experiment_exposes_scorecards_in_evidence_order() -> None:
    experiment = create_experiment()

    assert experiment.scorecards == (
        experiment.evidence[0].scorecard,
        experiment.evidence[1].scorecard,
    )


def test_experiment_records_ranking() -> None:
    experiment = create_experiment()

    assert len(experiment.ranking.entries) == 2


def test_experiment_exposes_winner() -> None:
    experiment = create_experiment()

    assert experiment.winner.overall_score == 0.9


def test_experiment_rejects_empty_evidence() -> None:
    with pytest.raises(
        ValidationError,
    ):
        WorkflowExperimentResult(
            evidence=(),
            ranking=WorkflowRanking(
                entries=(
                    RankedWorkflow(
                        rank=1,
                        scorecard=create_scorecard(
                            1.0,
                        ),
                    ),
                ),
            ),
        )


def test_experiment_evidence_is_immutable() -> None:
    experiment = create_experiment()

    with pytest.raises(
        ValidationError,
    ):
        experiment.evidence[0].scorecard = create_scorecard(0.5)


def test_experiment_is_immutable() -> None:
    experiment = create_experiment()

    with pytest.raises(
        ValidationError,
    ):
        experiment.evidence = ()


def test_experiment_round_trips_through_json() -> None:
    experiment = create_experiment()

    restored = WorkflowExperimentResult.model_validate_json(
        experiment.model_dump_json(),
    )

    assert restored == experiment
    assert restored.scorecards == experiment.scorecards

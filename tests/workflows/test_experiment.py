"""Tests for workflow experiment results."""

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    RankedWorkflow,
    WorkflowExperimentResult,
    WorkflowRanking,
    WorkflowScorecard,
)


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


def create_experiment() -> WorkflowExperimentResult:
    """Create a deterministic workflow experiment."""

    winner = create_scorecard(
        0.9,
    )

    runner_up = create_scorecard(
        0.7,
    )

    return WorkflowExperimentResult(
        scorecards=(
            winner,
            runner_up,
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


def test_experiment_records_scorecards() -> None:
    experiment = create_experiment()

    assert len(experiment.scorecards) == 2


def test_experiment_records_ranking() -> None:
    experiment = create_experiment()

    assert len(experiment.ranking.entries) == 2


def test_experiment_exposes_winner() -> None:
    experiment = create_experiment()

    assert experiment.winner.overall_score == 0.9


def test_experiment_rejects_empty_scorecards() -> None:
    with pytest.raises(
        ValidationError,
    ):
        WorkflowExperimentResult(
            scorecards=(),
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


def test_experiment_is_immutable() -> None:
    experiment = create_experiment()

    with pytest.raises(
        ValidationError,
    ):
        experiment.scorecards = ()


def test_experiment_round_trips_through_json() -> None:
    experiment = create_experiment()

    restored = WorkflowExperimentResult.model_validate_json(
        experiment.model_dump_json(),
    )

    assert restored == experiment

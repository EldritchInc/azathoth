"""Tests for workflow ranking models."""

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    RankedWorkflow,
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


def create_ranking() -> WorkflowRanking:
    """Create a deterministic workflow ranking."""

    return WorkflowRanking(
        entries=(
            RankedWorkflow(
                rank=1,
                scorecard=create_scorecard(
                    0.9,
                ),
            ),
            RankedWorkflow(
                rank=2,
                scorecard=create_scorecard(
                    0.7,
                ),
            ),
            RankedWorkflow(
                rank=3,
                scorecard=create_scorecard(
                    0.5,
                ),
            ),
        ),
    )


def test_ranking_records_entries() -> None:
    ranking = create_ranking()

    assert len(ranking.entries) == 3


def test_ranking_records_ranks() -> None:
    ranking = create_ranking()

    assert tuple(entry.rank for entry in ranking.entries) == (
        1,
        2,
        3,
    )


def test_ranking_exposes_winner() -> None:
    ranking = create_ranking()

    assert ranking.winner.overall_score == 0.9


def test_ranking_rejects_empty_entries() -> None:
    with pytest.raises(
        ValidationError,
    ):
        WorkflowRanking(
            entries=(),
        )


def test_ranking_rejects_nonconsecutive_ranks() -> None:
    with pytest.raises(
        ValidationError,
    ):
        WorkflowRanking(
            entries=(
                RankedWorkflow(
                    rank=1,
                    scorecard=create_scorecard(
                        1.0,
                    ),
                ),
                RankedWorkflow(
                    rank=3,
                    scorecard=create_scorecard(
                        0.5,
                    ),
                ),
            ),
        )


def test_rank_must_be_positive() -> None:
    with pytest.raises(
        ValidationError,
    ):
        RankedWorkflow(
            rank=0,
            scorecard=create_scorecard(
                1.0,
            ),
        )


def test_ranking_is_immutable() -> None:
    ranking = create_ranking()

    with pytest.raises(
        ValidationError,
    ):
        ranking.entries = ()


def test_ranking_round_trips_through_json() -> None:
    ranking = create_ranking()

    restored = WorkflowRanking.model_validate_json(
        ranking.model_dump_json(),
    )

    assert restored == ranking

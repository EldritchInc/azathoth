"""Tests for deterministic workflow scorecard ranking."""

import pytest

from azathoth.workflows import (
    WorkflowRanker,
    WorkflowScorecard,
)


def create_scorecard(
    *,
    quality_score: float = 0.5,
    reliability_score: float = 0.5,
    latency_score: float = 0.5,
    cost_score: float = 0.5,
    overall_score: float = 0.5,
    rationale: str = "",
) -> WorkflowScorecard:
    """Create a deterministic workflow scorecard."""

    return WorkflowScorecard(
        quality_score=quality_score,
        reliability_score=reliability_score,
        latency_score=latency_score,
        cost_score=cost_score,
        overall_score=overall_score,
        rationale=rationale,
    )


def test_ranker_orders_by_overall_score() -> None:
    """Higher overall scores should rank first."""

    low = create_scorecard(
        overall_score=0.4,
    )
    high = create_scorecard(
        overall_score=0.9,
    )
    middle = create_scorecard(
        overall_score=0.7,
    )

    ranking = WorkflowRanker().rank(
        (
            low,
            high,
            middle,
        )
    )

    assert tuple(entry.scorecard for entry in ranking.entries) == (
        high,
        middle,
        low,
    )


def test_ranker_uses_quality_score_as_first_tiebreaker() -> None:
    """Quality should break ties in overall score."""

    lower_quality = create_scorecard(
        overall_score=0.8,
        quality_score=0.6,
    )
    higher_quality = create_scorecard(
        overall_score=0.8,
        quality_score=0.9,
    )

    ranking = WorkflowRanker().rank(
        (
            lower_quality,
            higher_quality,
        )
    )

    assert ranking.entries[0].scorecard == higher_quality


def test_ranker_uses_reliability_score_as_second_tiebreaker() -> None:
    """Reliability should break ties after overall and quality."""

    lower_reliability = create_scorecard(
        overall_score=0.8,
        quality_score=0.9,
        reliability_score=0.6,
    )
    higher_reliability = create_scorecard(
        overall_score=0.8,
        quality_score=0.9,
        reliability_score=0.9,
    )

    ranking = WorkflowRanker().rank(
        (
            lower_reliability,
            higher_reliability,
        )
    )

    assert ranking.entries[0].scorecard == higher_reliability


def test_ranker_uses_latency_score_as_third_tiebreaker() -> None:
    """Latency should break ties after reliability."""

    lower_latency = create_scorecard(
        overall_score=0.8,
        quality_score=0.9,
        reliability_score=0.9,
        latency_score=0.6,
    )
    higher_latency = create_scorecard(
        overall_score=0.8,
        quality_score=0.9,
        reliability_score=0.9,
        latency_score=0.9,
    )

    ranking = WorkflowRanker().rank(
        (
            lower_latency,
            higher_latency,
        )
    )

    assert ranking.entries[0].scorecard == higher_latency


def test_ranker_uses_cost_score_as_final_score_tiebreaker() -> None:
    """Cost should break ties after all other score dimensions."""

    lower_cost = create_scorecard(
        overall_score=0.8,
        quality_score=0.9,
        reliability_score=0.9,
        latency_score=0.9,
        cost_score=0.6,
    )
    higher_cost = create_scorecard(
        overall_score=0.8,
        quality_score=0.9,
        reliability_score=0.9,
        latency_score=0.9,
        cost_score=0.9,
    )

    ranking = WorkflowRanker().rank(
        (
            lower_cost,
            higher_cost,
        )
    )

    assert ranking.entries[0].scorecard == higher_cost


def test_ranker_preserves_input_order_for_exact_ties() -> None:
    """Exact score ties should preserve reproducible input order."""

    first = create_scorecard(
        rationale="first",
    )
    second = create_scorecard(
        rationale="second",
    )
    third = create_scorecard(
        rationale="third",
    )

    ranking = WorkflowRanker().rank(
        (
            first,
            second,
            third,
        )
    )

    assert tuple(entry.scorecard.rationale for entry in ranking.entries) == (
        "first",
        "second",
        "third",
    )


def test_ranker_assigns_consecutive_ranks() -> None:
    """Ranked workflows should receive consecutive positions."""

    ranking = WorkflowRanker().rank(
        (
            create_scorecard(
                overall_score=0.2,
            ),
            create_scorecard(
                overall_score=0.9,
            ),
            create_scorecard(
                overall_score=0.5,
            ),
        )
    )

    assert tuple(entry.rank for entry in ranking.entries) == (
        1,
        2,
        3,
    )


def test_ranker_exposes_highest_ranked_scorecard_as_winner() -> None:
    """Ranking winner should be the strongest scorecard."""

    winner = create_scorecard(
        overall_score=1.0,
    )

    ranking = WorkflowRanker().rank(
        (
            create_scorecard(
                overall_score=0.2,
            ),
            winner,
            create_scorecard(
                overall_score=0.7,
            ),
        )
    )

    assert ranking.winner == winner


def test_ranker_rejects_empty_scorecards() -> None:
    """At least one workflow scorecard is required."""

    with pytest.raises(
        ValueError,
        match="At least one workflow scorecard is required for ranking.",
    ):
        WorkflowRanker().rank(())

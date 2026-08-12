"""Tests for deterministic workflow scorecard ranking."""

from itertools import permutations

import pytest
from pydantic import ValidationError

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


def test_ranker_is_independent_of_input_order_when_scores_differ() -> None:
    """Distinct scorecards should rank identically across all permutations."""

    strongest = create_scorecard(
        overall_score=0.9,
        rationale="strongest",
    )

    middle = create_scorecard(
        overall_score=0.7,
        rationale="middle",
    )

    weakest = create_scorecard(
        overall_score=0.5,
        rationale="weakest",
    )

    expected = (
        "strongest",
        "middle",
        "weakest",
    )

    for candidate_order in permutations(
        (
            strongest,
            middle,
            weakest,
        )
    ):
        ranking = WorkflowRanker().rank(candidate_order)

        assert tuple(entry.scorecard.rationale for entry in ranking.entries) == expected


def test_ranker_applies_complete_tiebreaker_chain() -> None:
    """Ranking should use every score dimension in declared order."""

    overall_winner = create_scorecard(
        overall_score=0.9,
        quality_score=0.1,
        reliability_score=0.1,
        latency_score=0.1,
        cost_score=0.1,
        rationale="overall",
    )

    quality_winner = create_scorecard(
        overall_score=0.8,
        quality_score=0.9,
        reliability_score=0.1,
        latency_score=0.1,
        cost_score=0.1,
        rationale="quality",
    )

    reliability_winner = create_scorecard(
        overall_score=0.8,
        quality_score=0.8,
        reliability_score=0.9,
        latency_score=0.1,
        cost_score=0.1,
        rationale="reliability",
    )

    latency_winner = create_scorecard(
        overall_score=0.8,
        quality_score=0.8,
        reliability_score=0.8,
        latency_score=0.9,
        cost_score=0.1,
        rationale="latency",
    )

    cost_winner = create_scorecard(
        overall_score=0.8,
        quality_score=0.8,
        reliability_score=0.8,
        latency_score=0.8,
        cost_score=0.9,
        rationale="cost",
    )

    ranking = WorkflowRanker().rank(
        (
            cost_winner,
            latency_winner,
            reliability_winner,
            quality_winner,
            overall_winner,
        )
    )

    assert tuple(entry.scorecard.rationale for entry in ranking.entries) == (
        "overall",
        "quality",
        "reliability",
        "latency",
        "cost",
    )


def test_ranker_does_not_use_rationale_as_ranking_evidence() -> None:
    """Descriptive rationale should not affect exact score ties."""

    first = create_scorecard(
        rationale="zeta",
    )

    second = create_scorecard(
        rationale="alpha",
    )

    ranking = WorkflowRanker().rank(
        (
            first,
            second,
        )
    )

    assert ranking.entries[0].scorecard == first
    assert ranking.entries[1].scorecard == second


def test_ranker_handles_boundary_scores() -> None:
    """Ranking should correctly order normalized boundary scores."""

    worst = create_scorecard(
        quality_score=0.0,
        reliability_score=0.0,
        latency_score=0.0,
        cost_score=0.0,
        overall_score=0.0,
    )

    best = create_scorecard(
        quality_score=1.0,
        reliability_score=1.0,
        latency_score=1.0,
        cost_score=1.0,
        overall_score=1.0,
    )

    ranking = WorkflowRanker().rank(
        (
            worst,
            best,
        )
    )

    assert ranking.winner == best

    assert tuple(entry.scorecard for entry in ranking.entries) == (
        best,
        worst,
    )


def test_ranker_returns_immutable_ranking() -> None:
    """Rankings produced by the ranker should remain immutable."""

    ranking = WorkflowRanker().rank(
        (
            create_scorecard(
                overall_score=0.9,
            ),
            create_scorecard(
                overall_score=0.5,
            ),
        )
    )

    with pytest.raises(
        ValidationError,
    ):
        ranking.entries = ()


def test_ranker_result_round_trips_through_json() -> None:
    """Rankings produced by the ranker should survive JSON serialization."""

    ranking = WorkflowRanker().rank(
        (
            create_scorecard(
                overall_score=0.9,
                rationale="winner",
            ),
            create_scorecard(
                overall_score=0.5,
                rationale="runner-up",
            ),
        )
    )

    restored = type(ranking).model_validate_json(ranking.model_dump_json())

    assert restored == ranking
    assert restored.winner == ranking.winner

"""Tests for combining workflow scorecards across benchmark cases."""

import pytest

from azathoth.workflows import (
    WorkflowScorecard,
    aggregate_workflow_scorecards,
)


def create_scorecard(
    *,
    quality: float,
    reliability: float,
    latency: float,
    cost: float,
) -> WorkflowScorecard:
    """Create one scorecard whose overall score is the mean of its dimensions."""

    return WorkflowScorecard(
        quality_score=quality,
        reliability_score=reliability,
        latency_score=latency,
        cost_score=cost,
        overall_score=(quality + reliability + latency + cost) / 4.0,
        rationale="Per-case score.",
    )


def test_aggregation_averages_every_dimension() -> None:
    aggregate = aggregate_workflow_scorecards(
        (
            create_scorecard(
                quality=1.0,
                reliability=1.0,
                latency=0.5,
                cost=1.0,
            ),
            create_scorecard(
                quality=0.0,
                reliability=0.5,
                latency=1.0,
                cost=0.5,
            ),
        ),
        rationale="Combined.",
    )

    assert aggregate.quality_score == pytest.approx(0.5)
    assert aggregate.reliability_score == pytest.approx(0.75)
    assert aggregate.latency_score == pytest.approx(0.75)
    assert aggregate.cost_score == pytest.approx(0.75)
    assert aggregate.overall_score == pytest.approx((0.875 + 0.5) / 2.0)
    assert aggregate.rationale == "Combined."


def test_aggregation_of_one_scorecard_keeps_its_scores() -> None:
    scorecard = create_scorecard(
        quality=0.25,
        reliability=0.5,
        latency=0.75,
        cost=1.0,
    )

    aggregate = aggregate_workflow_scorecards(
        (scorecard,),
        rationale="Single case.",
    )

    assert aggregate == scorecard.model_copy(
        update={
            "rationale": "Single case.",
        },
    )


def test_aggregation_rejects_empty_collection() -> None:
    with pytest.raises(
        ValueError,
        match="^Cannot aggregate an empty collection of workflow scorecards.$",
    ):
        aggregate_workflow_scorecards(
            (),
            rationale="Nothing.",
        )

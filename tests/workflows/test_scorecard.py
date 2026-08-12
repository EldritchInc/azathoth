"""Tests for workflow scorecards."""

import pytest
from pydantic import ValidationError

from azathoth.workflows import WorkflowScorecard


def create_scorecard() -> WorkflowScorecard:
    """Create a deterministic workflow scorecard."""

    return WorkflowScorecard(
        quality_score=0.9,
        reliability_score=0.8,
        latency_score=0.7,
        cost_score=0.6,
        overall_score=0.75,
        rationale="Balanced workflow performance.",
    )


def test_scorecard_records_dimension_scores() -> None:
    scorecard = create_scorecard()

    assert scorecard.quality_score == 0.9
    assert scorecard.reliability_score == 0.8
    assert scorecard.latency_score == 0.7
    assert scorecard.cost_score == 0.6


def test_scorecard_records_overall_score() -> None:
    scorecard = create_scorecard()

    assert scorecard.overall_score == 0.75


def test_scorecard_records_rationale() -> None:
    scorecard = create_scorecard()

    assert scorecard.rationale == "Balanced workflow performance."


def test_scorecard_defaults_to_empty_rationale() -> None:
    scorecard = WorkflowScorecard(
        quality_score=1.0,
        reliability_score=1.0,
        latency_score=1.0,
        cost_score=1.0,
        overall_score=1.0,
    )

    assert scorecard.rationale == ""


def test_scorecard_rejects_scores_below_zero() -> None:
    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=-0.01,
            reliability_score=0.5,
            latency_score=0.5,
            cost_score=0.5,
            overall_score=0.5,
        )

    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=0.5,
            reliability_score=-0.01,
            latency_score=0.5,
            cost_score=0.5,
            overall_score=0.5,
        )

    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=0.5,
            reliability_score=0.5,
            latency_score=-0.01,
            cost_score=0.5,
            overall_score=0.5,
        )

    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=0.5,
            reliability_score=0.5,
            latency_score=0.5,
            cost_score=-0.01,
            overall_score=0.5,
        )

    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=0.5,
            reliability_score=0.5,
            latency_score=0.5,
            cost_score=0.5,
            overall_score=-0.01,
        )


def test_scorecard_rejects_scores_above_one() -> None:
    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=1.01,
            reliability_score=0.5,
            latency_score=0.5,
            cost_score=0.5,
            overall_score=0.5,
        )

    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=0.5,
            reliability_score=1.01,
            latency_score=0.5,
            cost_score=0.5,
            overall_score=0.5,
        )

    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=0.5,
            reliability_score=0.5,
            latency_score=1.01,
            cost_score=0.5,
            overall_score=0.5,
        )

    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=0.5,
            reliability_score=0.5,
            latency_score=0.5,
            cost_score=1.01,
            overall_score=0.5,
        )

    with pytest.raises(ValidationError):
        WorkflowScorecard(
            quality_score=0.5,
            reliability_score=0.5,
            latency_score=0.5,
            cost_score=0.5,
            overall_score=1.01,
        )


def test_scorecard_accepts_boundary_scores() -> None:
    scorecard = WorkflowScorecard(
        quality_score=0.0,
        reliability_score=1.0,
        latency_score=0.0,
        cost_score=1.0,
        overall_score=0.5,
    )

    assert scorecard.quality_score == 0.0
    assert scorecard.reliability_score == 1.0
    assert scorecard.latency_score == 0.0
    assert scorecard.cost_score == 1.0
    assert scorecard.overall_score == 0.5


def test_scorecard_is_immutable() -> None:
    scorecard = create_scorecard()

    with pytest.raises(ValidationError):
        scorecard.overall_score = 1.0


def test_scorecard_round_trips_through_json() -> None:
    scorecard = create_scorecard()

    restored = WorkflowScorecard.model_validate_json(scorecard.model_dump_json())

    assert restored == scorecard

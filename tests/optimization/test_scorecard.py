"""Tests for aggregated strategy optimization scorecards."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.evaluation import (
    EvaluationResult,
    EvaluationStatus,
)
from azathoth.execution import ExecutionResult
from azathoth.optimization import (
    OptimizationRun,
    StrategyScorecard,
)
from azathoth.strategies import StrategyMetadata

STRATEGY_ID = UUID("e5e88510-cfa8-4cf1-b966-64268f80b44f")
EXAMPLE_ID_1 = UUID("60c664ad-1909-48d5-8362-5234eb76dcb0")
EXAMPLE_ID_2 = UUID("2caf60eb-6a91-4d88-ae35-f2d49ed42de3")
EXAMPLE_ID_3 = UUID("29bcf2e0-96ec-41b0-b899-207bd5b4fefc")


def create_strategy_metadata() -> StrategyMetadata:
    """Create deterministic strategy metadata."""

    return StrategyMetadata(
        id=STRATEGY_ID,
        name="Extract support intent",
        description="Extract the intent from the latest support event.",
        version="1.0.0",
    )


def create_run(
    *,
    example_id: UUID,
    score: float,
    passed: bool,
    strategy_id: UUID = STRATEGY_ID,
    strategy_name: str = "Extract support intent",
    strategy_version: str = "1.0.0",
) -> OptimizationRun:
    """Create a deterministic optimization run."""

    now = datetime(
        2026,
        7,
        31,
        15,
        0,
        tzinfo=UTC,
    )

    execution = ExecutionResult(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        output="duplicate_charge",
        initial_context=Context(),
        final_context=Context(),
        started_at=now,
        completed_at=now,
    )

    evaluation = EvaluationResult(
        evaluator_name="test-evaluator",
        evaluator_version="1.0.0",
        score=score,
        threshold=0.5,
        status=(EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED),
        reason="Deterministic scorecard test result.",
    )

    return OptimizationRun(
        example_id=example_id,
        execution=execution,
        evaluation=evaluation,
        started_at=now,
        completed_at=now,
    )


def test_scorecard_derives_metrics_from_runs() -> None:
    scorecard = StrategyScorecard(
        strategy=create_strategy_metadata(),
        runs=(
            create_run(
                example_id=EXAMPLE_ID_1,
                score=1.0,
                passed=True,
            ),
            create_run(
                example_id=EXAMPLE_ID_2,
                score=0.75,
                passed=True,
            ),
            create_run(
                example_id=EXAMPLE_ID_3,
                score=0.25,
                passed=False,
            ),
        ),
    )

    assert scorecard.run_count == 3
    assert scorecard.passed_count == 2
    assert scorecard.pass_rate == pytest.approx(2 / 3)
    assert scorecard.mean_score == pytest.approx(2 / 3)


def test_scorecard_serializes_computed_metrics() -> None:
    scorecard = StrategyScorecard(
        strategy=create_strategy_metadata(),
        runs=(
            create_run(
                example_id=EXAMPLE_ID_1,
                score=1.0,
                passed=True,
            ),
            create_run(
                example_id=EXAMPLE_ID_2,
                score=0.0,
                passed=False,
            ),
        ),
    )

    serialized = scorecard.model_dump()

    assert serialized["run_count"] == 2
    assert serialized["passed_count"] == 1
    assert serialized["pass_rate"] == 0.5
    assert serialized["mean_score"] == 0.5


def test_scorecard_requires_at_least_one_run() -> None:
    with pytest.raises(ValidationError):
        StrategyScorecard(
            strategy=create_strategy_metadata(),
            runs=(),
        )


def test_scorecard_rejects_run_from_different_strategy() -> None:
    mismatched_run = create_run(
        example_id=EXAMPLE_ID_1,
        score=1.0,
        passed=True,
        strategy_id=UUID("6b8f8ddf-da56-4fc5-9921-d185e18e894c"),
    )

    with pytest.raises(
        ValidationError,
        match="Every optimization run must belong to the scorecard strategy",
    ):
        StrategyScorecard(
            strategy=create_strategy_metadata(),
            runs=(mismatched_run,),
        )


def test_scorecard_rejects_run_from_different_strategy_version() -> None:
    mismatched_run = create_run(
        example_id=EXAMPLE_ID_1,
        score=1.0,
        passed=True,
        strategy_version="2.0.0",
    )

    with pytest.raises(
        ValidationError,
        match="Every optimization run must belong to the scorecard strategy",
    ):
        StrategyScorecard(
            strategy=create_strategy_metadata(),
            runs=(mismatched_run,),
        )


def test_scorecard_is_immutable() -> None:
    scorecard = StrategyScorecard(
        strategy=create_strategy_metadata(),
        runs=(
            create_run(
                example_id=EXAMPLE_ID_1,
                score=1.0,
                passed=True,
            ),
        ),
    )

    with pytest.raises(ValidationError):
        scorecard.runs = ()


def test_scorecard_round_trips_through_json() -> None:
    scorecard = StrategyScorecard(
        strategy=create_strategy_metadata(),
        runs=(
            create_run(
                example_id=EXAMPLE_ID_1,
                score=1.0,
                passed=True,
            ),
            create_run(
                example_id=EXAMPLE_ID_2,
                score=0.0,
                passed=False,
            ),
        ),
    )

    serialized = scorecard.model_dump_json()
    restored = StrategyScorecard.model_validate_json(serialized)

    assert restored.strategy == scorecard.strategy
    assert restored.runs == scorecard.runs
    assert restored.run_count == scorecard.run_count
    assert restored.pass_rate == scorecard.pass_rate
    assert restored.mean_score == scorecard.mean_score

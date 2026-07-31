"""Tests for deterministic strategy ranking."""

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
    RankedStrategy,
    StrategyRanker,
    StrategyRanking,
    StrategyScorecard,
)
from azathoth.strategies import StrategyMetadata


def create_run(
    *,
    strategy: StrategyMetadata,
    example_id: UUID,
    score: float,
) -> OptimizationRun:
    """Create a deterministic optimization run."""

    now = datetime(2026, 7, 31, 16, 0, tzinfo=UTC)
    passed = score >= 0.5

    return OptimizationRun(
        example_id=example_id,
        execution=ExecutionResult(
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            output=None,
            initial_context=Context(),
            final_context=Context(),
            started_at=now,
            completed_at=now,
        ),
        evaluation=EvaluationResult(
            evaluator_name="test-evaluator",
            evaluator_version="1.0.0",
            score=score,
            threshold=0.5,
            status=(EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED),
            reason="Deterministic ranking test result.",
        ),
        started_at=now,
        completed_at=now,
    )


def create_scorecard(
    *,
    strategy_id: UUID,
    name: str,
    scores: tuple[float, ...],
    version: str = "1.0.0",
) -> StrategyScorecard:
    """Create a deterministic strategy scorecard."""

    metadata = StrategyMetadata(
        id=strategy_id,
        name=name,
        description=f"Ranking test strategy {name}.",
        version=version,
    )

    return StrategyScorecard(
        strategy=metadata,
        runs=tuple(
            create_run(
                strategy=metadata,
                example_id=UUID(int=index + 1),
                score=score,
            )
            for index, score in enumerate(scores)
        ),
    )


def test_ranker_prefers_higher_pass_rate() -> None:
    weaker = create_scorecard(
        strategy_id=UUID("11111111-1111-1111-1111-111111111111"),
        name="Weaker",
        scores=(1.0, 0.0),
    )
    stronger = create_scorecard(
        strategy_id=UUID("22222222-2222-2222-2222-222222222222"),
        name="Stronger",
        scores=(0.6, 0.6),
    )

    ranking = StrategyRanker().rank((weaker, stronger))

    assert ranking.winner == stronger
    assert ranking.entries[0].rank == 1
    assert ranking.entries[1].rank == 2


def test_ranker_uses_mean_score_after_pass_rate() -> None:
    lower_mean = create_scorecard(
        strategy_id=UUID("33333333-3333-3333-3333-333333333333"),
        name="Lower mean",
        scores=(0.6, 0.6),
    )
    higher_mean = create_scorecard(
        strategy_id=UUID("44444444-4444-4444-4444-444444444444"),
        name="Higher mean",
        scores=(0.9, 0.8),
    )

    ranking = StrategyRanker().rank((lower_mean, higher_mean))

    assert ranking.winner == higher_mean


def test_ranker_breaks_complete_ties_deterministically() -> None:
    later_id = create_scorecard(
        strategy_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        name="Later",
        scores=(1.0,),
    )
    earlier_id = create_scorecard(
        strategy_id=UUID("00000000-0000-0000-0000-000000000001"),
        name="Earlier",
        scores=(1.0,),
    )

    ranking = StrategyRanker().rank((later_id, earlier_id))

    assert ranking.winner == earlier_id


def test_ranker_does_not_mutate_or_depend_on_input_order() -> None:
    first = create_scorecard(
        strategy_id=UUID("55555555-5555-5555-5555-555555555555"),
        name="First",
        scores=(0.0,),
    )
    second = create_scorecard(
        strategy_id=UUID("66666666-6666-6666-6666-666666666666"),
        name="Second",
        scores=(1.0,),
    )
    scorecards = (first, second)

    ranking = StrategyRanker().rank(scorecards)

    assert scorecards == (first, second)
    assert ranking.winner == second


def test_ranker_rejects_empty_scorecards() -> None:
    with pytest.raises(
        ValueError,
        match="At least one strategy scorecard",
    ):
        StrategyRanker().rank(())


def test_strategy_ranking_requires_consecutive_ranks() -> None:
    scorecard = create_scorecard(
        strategy_id=UUID("77777777-7777-7777-7777-777777777777"),
        name="Candidate",
        scores=(1.0,),
    )

    with pytest.raises(
        ValidationError,
        match="consecutive ranks",
    ):
        StrategyRanking(
            entries=(
                RankedStrategy(
                    rank=2,
                    scorecard=scorecard,
                ),
            )
        )


def test_strategy_ranking_round_trips_through_json() -> None:
    first = create_scorecard(
        strategy_id=UUID("88888888-8888-8888-8888-888888888888"),
        name="First",
        scores=(1.0,),
    )
    second = create_scorecard(
        strategy_id=UUID("99999999-9999-9999-9999-999999999999"),
        name="Second",
        scores=(0.0,),
    )

    ranking = StrategyRanker().rank((second, first))

    restored = StrategyRanking.model_validate_json(ranking.model_dump_json())

    assert restored.entries == ranking.entries
    assert restored.winner == ranking.winner

"""Deterministic ranking of candidate strategy scorecards."""

from collections.abc import Sequence

from azathoth.optimization.models import (
    RankedStrategy,
    StrategyRanking,
    StrategyScorecard,
)


class StrategyRanker:
    """Rank candidate strategies using recorded experiment evidence."""

    def rank(
        self,
        scorecards: Sequence[StrategyScorecard],
    ) -> StrategyRanking:
        """Return scorecards ordered from strongest to weakest."""

        if not scorecards:
            raise ValueError("At least one strategy scorecard is required for ranking.")

        ordered = sorted(
            scorecards,
            key=lambda scorecard: (
                -scorecard.pass_rate,
                -scorecard.mean_score,
                -scorecard.run_count,
                str(scorecard.strategy.id),
                scorecard.strategy.version,
            ),
        )

        return StrategyRanking(
            entries=tuple(
                RankedStrategy(
                    rank=index,
                    scorecard=scorecard,
                )
                for index, scorecard in enumerate(ordered, start=1)
            )
        )

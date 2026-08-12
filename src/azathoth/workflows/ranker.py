"""Deterministic ranking of workflow scorecards."""

from collections.abc import Sequence

from azathoth.workflows.ranking import (
    RankedWorkflow,
    WorkflowRanking,
)
from azathoth.workflows.scorecard import (
    WorkflowScorecard,
)


class WorkflowRanker:
    """Rank workflow scorecards using normalized scoring evidence."""

    def rank(
        self,
        scorecards: Sequence[WorkflowScorecard],
    ) -> WorkflowRanking:
        """Return scorecards ordered from strongest to weakest."""

        if not scorecards:
            raise ValueError("At least one workflow scorecard is required for ranking.")

        ordered = sorted(
            scorecards,
            key=lambda scorecard: (
                -scorecard.overall_score,
                -scorecard.quality_score,
                -scorecard.reliability_score,
                -scorecard.latency_score,
                -scorecard.cost_score,
            ),
        )

        return WorkflowRanking(
            entries=tuple(
                RankedWorkflow(
                    rank=index,
                    scorecard=scorecard,
                )
                for index, scorecard in enumerate(
                    ordered,
                    start=1,
                )
            )
        )

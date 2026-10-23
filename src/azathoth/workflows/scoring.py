"""Deterministic workflow scorecard calculation."""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from azathoth.evaluation import EvaluationResult
from azathoth.workflows.execution import (
    WorkflowRun,
)
from azathoth.workflows.scorecard import (
    WorkflowScorecard,
)


class WorkflowScoringPolicy(BaseModel):
    """Configure canonical workflow score normalization targets."""

    model_config = ConfigDict(frozen=True)

    target_latency_seconds: float = Field(
        gt=0.0,
    )
    target_cost_usd: float = Field(
        gt=0.0,
    )


class WorkflowScorer:
    """Convert workflow execution evidence into a normalized scorecard."""

    def __init__(
        self,
        *,
        policy: WorkflowScoringPolicy,
    ) -> None:
        self._policy = policy

    @property
    def policy(self) -> WorkflowScoringPolicy:
        """Return the configured workflow scoring policy."""

        return self._policy

    def score(
        self,
        *,
        run: WorkflowRun,
        evaluation: EvaluationResult,
    ) -> WorkflowScorecard:
        """Score one completed workflow run deterministically."""

        quality_score = evaluation.score

        reliability = run.reliability

        reliability_score = (
            reliability.completion_rate
            + reliability.first_attempt_success_rate
            + (1.0 - reliability.retry_rate)
            + (1.0 - reliability.failure_rate)
        ) / 4.0

        latency_score = self._normalized_target_score(
            actual=run.duration_seconds,
            target=self._policy.target_latency_seconds,
        )

        total_cost_usd = self._total_cost_usd(run)

        cost_score = self._normalized_target_score(
            actual=total_cost_usd,
            target=self._policy.target_cost_usd,
        )

        overall_score = (quality_score + reliability_score + latency_score + cost_score) / 4.0

        return WorkflowScorecard(
            quality_score=quality_score,
            reliability_score=reliability_score,
            latency_score=latency_score,
            cost_score=cost_score,
            overall_score=overall_score,
            rationale=(
                "Canonical workflow score calculated from quality, reliability, latency, and cost."
            ),
        )

    @staticmethod
    def _normalized_target_score(
        *,
        actual: float,
        target: float,
    ) -> float:
        """Normalize a lower-is-better measurement against its target."""

        if actual <= target:
            return 1.0

        return target / actual

    @staticmethod
    def _total_cost_usd(
        run: WorkflowRun,
    ) -> float:
        """Return total known cost across successful workflow executions."""

        total_cost_usd = 0.0

        for step in run.steps:
            if step.execution is None:
                continue

            metrics = step.execution.metrics

            if metrics is None or metrics.estimated_cost_usd is None:
                raise ValueError(
                    "Executed workflow steps must provide estimated cost metrics for scoring."
                )

            total_cost_usd += metrics.estimated_cost_usd

        return total_cost_usd


def aggregate_workflow_scorecards(
    scorecards: Sequence[WorkflowScorecard],
    *,
    rationale: str,
) -> WorkflowScorecard:
    """Return the per-dimension mean of several workflow scorecards.

    Every dimension, including the overall score, is the unweighted mean of
    that dimension across the scorecards, so each scorecard counts equally.

    Raises:
        ValueError: No scorecards were supplied.
    """

    if not scorecards:
        raise ValueError("Cannot aggregate an empty collection of workflow scorecards.")

    count = len(scorecards)

    return WorkflowScorecard(
        quality_score=sum(item.quality_score for item in scorecards) / count,
        reliability_score=sum(item.reliability_score for item in scorecards) / count,
        latency_score=sum(item.latency_score for item in scorecards) / count,
        cost_score=sum(item.cost_score for item in scorecards) / count,
        overall_score=sum(item.overall_score for item in scorecards) / count,
        rationale=rationale,
    )

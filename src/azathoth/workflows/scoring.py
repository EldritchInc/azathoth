"""Deterministic workflow scorecard calculation."""

from collections.abc import Mapping, Sequence
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from azathoth.citations import VERIFIED_STATUSES
from azathoth.evaluation import EvaluationResult
from azathoth.prompting import CITATIONS_RESOURCE_KIND
from azathoth.providers import BEDROCK_PRICING_VARIABLE, BEDROCK_PROVIDER
from azathoth.strategies import StrategyExecutionMetrics
from azathoth.workflows.execution import (
    WorkflowRun,
)
from azathoth.workflows.run_failure import (
    RUN_FAILURE_EVALUATOR_NAME,
)
from azathoth.workflows.scorecard import (
    WorkflowScorecard,
)

CITED_RATIONALE: Final = (
    "Canonical workflow score calculated from quality, reliability, latency, cost, and citations."
)
"""The rationale of a scorecard of a run whose cited steps kept their checks."""


def run_citation_score(
    run: WorkflowRun,
) -> float | None:
    """Return the fraction of citations a run's cited steps kept that verified (ADR 0117).

    It is read from the counts each step's `citations` resource records
    (ADR 0116): its verified and normalized-verified citations, over every
    citation. A run whose cited steps checked no citation scores 0, since it
    cited nothing; a run with no cited step has no citation score.
    """

    records = [
        resource.attributes
        for step in run.steps
        if step.execution is not None
        for resource in step.execution.resources
        if resource.kind == CITATIONS_RESOURCE_KIND
    ]

    if not records:
        return None

    checked = sum(_count(record, "citations") for record in records)
    verified = sum(
        _count(record, status.value) for record in records for status in VERIFIED_STATUSES
    )

    return min(verified / checked, 1.0) if checked else 0.0


def _count(
    attributes: Mapping[str, JsonValue],
    key: str,
) -> int:
    """Return one count a citations resource records, or 0 when it records none."""

    value = attributes.get(key)

    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


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
        """Score one completed workflow run deterministically.

        A run judged by the run-failure evaluation failed without producing
        its declared result. It earns no latency or cost credit, because
        failing quickly and cheaply is not efficiency, so a crashing candidate
        can never outrank a correct one on speed or price alone.

        A run whose cited steps kept their checks is scored on its citations
        too, and its overall score is the mean of all five dimensions; any
        other run's is the mean of four, as it always was (ADR 0117).
        """

        quality_score = evaluation.score

        reliability = run.reliability

        reliability_score = (
            reliability.completion_rate
            + reliability.first_attempt_success_rate
            + (1.0 - reliability.retry_rate)
            + (1.0 - reliability.failure_rate)
        ) / 4.0

        if evaluation.evaluator_name == RUN_FAILURE_EVALUATOR_NAME:
            latency_score = 0.0
            cost_score = 0.0
        else:
            latency_score = self._normalized_target_score(
                actual=run.duration_seconds,
                target=self._policy.target_latency_seconds,
            )

            cost_score = self._normalized_target_score(
                actual=self._total_cost_usd(run),
                target=self._policy.target_cost_usd,
            )

        citation_score = run_citation_score(run)
        scores = (
            quality_score,
            reliability_score,
            latency_score,
            cost_score,
            *((citation_score,) if citation_score is not None else ()),
        )

        return WorkflowScorecard(
            quality_score=quality_score,
            reliability_score=reliability_score,
            latency_score=latency_score,
            cost_score=cost_score,
            citation_score=citation_score,
            overall_score=sum(scores) / len(scores),
            rationale=(
                CITED_RATIONALE
                if citation_score is not None
                else (
                    "Canonical workflow score calculated from quality, reliability, latency, "
                    "and cost."
                )
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

            if metrics is None:
                raise ValueError(
                    "Executed workflow steps must provide estimated cost metrics for scoring."
                )

            if metrics.estimated_cost_usd is None:
                raise ValueError(_unknown_cost(step.step_id, metrics))

            total_cost_usd += metrics.estimated_cost_usd

        return total_cost_usd


def _unknown_cost(
    step_id: UUID,
    metrics: StrategyExecutionMetrics,
) -> str:
    """Return why a step's unknown cost keeps its run from being scored (ADR 0103)."""

    if metrics.provider is None or metrics.model is None:
        return f"Workflow step {step_id} has no estimated cost, so its run cannot be scored."

    where = f" in {BEDROCK_PRICING_VARIABLE}" if metrics.provider == BEDROCK_PROVIDER else ""

    return (
        f"Workflow step {step_id} ran model {metrics.provider}/{metrics.model}, whose cost "
        f"is unknown; price the model{where} to score its run."
    )


def aggregate_workflow_scorecards(
    scorecards: Sequence[WorkflowScorecard],
    *,
    rationale: str,
) -> WorkflowScorecard:
    """Return the per-dimension mean of several workflow scorecards.

    Every dimension, including the overall score, is the unweighted mean of
    that dimension across the scorecards, so each scorecard counts equally.
    The citation score is the mean of the scorecards that have one, or None
    when none does (ADR 0117).

    Raises:
        ValueError: No scorecards were supplied.
    """

    if not scorecards:
        raise ValueError("Cannot aggregate an empty collection of workflow scorecards.")

    count = len(scorecards)
    cited = [item.citation_score for item in scorecards if item.citation_score is not None]

    return WorkflowScorecard(
        quality_score=sum(item.quality_score for item in scorecards) / count,
        reliability_score=sum(item.reliability_score for item in scorecards) / count,
        latency_score=sum(item.latency_score for item in scorecards) / count,
        cost_score=sum(item.cost_score for item in scorecards) / count,
        citation_score=sum(cited) / len(cited) if cited else None,
        overall_score=sum(item.overall_score for item in scorecards) / count,
        rationale=rationale,
    )

"""Tests for deterministic workflow scoring."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.evaluation import (
    EvaluationResult,
    EvaluationStatus,
)
from azathoth.execution import ExecutionResult
from azathoth.strategies import StrategyExecutionMetrics
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRun,
    WorkflowScorer,
    WorkflowScoringPolicy,
    WorkflowStepAttempt,
    WorkflowStepRun,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

STARTED_AT = datetime(
    2026,
    8,
    11,
    12,
    0,
    tzinfo=UTC,
)


def create_evaluation(
    *,
    score: float = 0.8,
) -> EvaluationResult:
    """Create a deterministic output evaluation."""

    return EvaluationResult(
        evaluator_name="test-evaluator",
        score=score,
        threshold=0.5,
        status=(EvaluationStatus.PASSED if score >= 0.5 else EvaluationStatus.FAILED),
        reason="Synthetic evaluation result.",
    )


def create_execution(
    *,
    duration_seconds: float = 5.0,
    estimated_cost_usd: float = 0.05,
) -> ExecutionResult:
    """Create a deterministic successful strategy execution."""

    completed_at = STARTED_AT + timedelta(
        seconds=duration_seconds,
    )

    context = Context()

    return ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="test-strategy",
        strategy_version="1.0.0",
        output="result",
        metrics=StrategyExecutionMetrics(
            provider="test-provider",
            model="test-model",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=int(duration_seconds * 1000),
            estimated_cost_usd=estimated_cost_usd,
        ),
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=completed_at,
    )


def create_run(
    *,
    duration_seconds: float = 5.0,
    estimated_cost_usd: float = 0.05,
) -> WorkflowRun:
    """Create a deterministic successful workflow run."""

    execution = create_execution(
        duration_seconds=duration_seconds,
        estimated_cost_usd=estimated_cost_usd,
    )

    attempt = WorkflowStepAttempt(
        attempt_number=1,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        execution=execution,
    )

    step = WorkflowStepRun(
        step_id=STEP_ID,
        layer_index=0,
        execution=execution,
        attempts=(attempt,),
    )

    return WorkflowRun(
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="test-workflow",
            description="Workflow used for scoring tests.",
        ),
        steps=(step,),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=STARTED_AT
        + timedelta(
            seconds=duration_seconds,
        ),
    )


def create_policy() -> WorkflowScoringPolicy:
    """Create the canonical scoring policy used by tests."""

    return WorkflowScoringPolicy(
        target_latency_seconds=10.0,
        target_cost_usd=0.10,
    )


def test_scoring_uses_evaluation_score_for_quality() -> None:
    """Workflow quality should come from the canonical evaluation domain."""

    scorecard = WorkflowScorer(
        policy=create_policy(),
    ).score(
        run=create_run(),
        evaluation=create_evaluation(
            score=0.8,
        ),
    )

    assert scorecard.quality_score == pytest.approx(0.8)


def test_scoring_gives_full_credit_within_latency_and_cost_targets() -> None:
    """Workflows meeting configured targets should receive full credit."""

    scorecard = WorkflowScorer(
        policy=create_policy(),
    ).score(
        run=create_run(
            duration_seconds=5.0,
            estimated_cost_usd=0.05,
        ),
        evaluation=create_evaluation(),
    )

    assert scorecard.reliability_score == pytest.approx(1.0)
    assert scorecard.latency_score == pytest.approx(1.0)
    assert scorecard.cost_score == pytest.approx(1.0)


def test_scoring_degrades_latency_and_cost_above_targets() -> None:
    """Scores above configured targets should degrade proportionally."""

    scorecard = WorkflowScorer(
        policy=create_policy(),
    ).score(
        run=create_run(
            duration_seconds=20.0,
            estimated_cost_usd=0.20,
        ),
        evaluation=create_evaluation(),
    )

    assert scorecard.latency_score == pytest.approx(0.5)
    assert scorecard.cost_score == pytest.approx(0.5)


def test_scoring_uses_equal_dimension_weights_for_overall_score() -> None:
    """Canonical overall scoring should average all four dimensions."""

    scorecard = WorkflowScorer(
        policy=create_policy(),
    ).score(
        run=create_run(
            duration_seconds=20.0,
            estimated_cost_usd=0.20,
        ),
        evaluation=create_evaluation(
            score=0.8,
        ),
    )

    assert scorecard.quality_score == pytest.approx(0.8)
    assert scorecard.reliability_score == pytest.approx(1.0)
    assert scorecard.latency_score == pytest.approx(0.5)
    assert scorecard.cost_score == pytest.approx(0.5)
    assert scorecard.overall_score == pytest.approx(0.7)


def test_scoring_records_canonical_rationale() -> None:
    """Canonical scoring should identify the evidence it used."""

    scorecard = WorkflowScorer(
        policy=create_policy(),
    ).score(
        run=create_run(),
        evaluation=create_evaluation(),
    )

    assert scorecard.rationale == (
        "Canonical workflow score calculated from quality, reliability, latency, and cost."
    )


def test_scoring_policy_rejects_zero_latency_target() -> None:
    """Latency targets must be strictly positive."""

    with pytest.raises(ValidationError):
        WorkflowScoringPolicy(
            target_latency_seconds=0.0,
            target_cost_usd=0.10,
        )


def test_scoring_policy_rejects_negative_latency_target() -> None:
    """Latency targets cannot be negative."""

    with pytest.raises(ValidationError):
        WorkflowScoringPolicy(
            target_latency_seconds=-1.0,
            target_cost_usd=0.10,
        )


def test_scoring_policy_rejects_zero_cost_target() -> None:
    """Cost targets must be strictly positive."""

    with pytest.raises(ValidationError):
        WorkflowScoringPolicy(
            target_latency_seconds=10.0,
            target_cost_usd=0.0,
        )


def test_scoring_policy_rejects_negative_cost_target() -> None:
    """Cost targets cannot be negative."""

    with pytest.raises(ValidationError):
        WorkflowScoringPolicy(
            target_latency_seconds=10.0,
            target_cost_usd=-0.01,
        )

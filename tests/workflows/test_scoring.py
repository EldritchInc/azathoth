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
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

SECOND_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")

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
    strategy_id: UUID = STRATEGY_ID,
    duration_seconds: float = 5.0,
    estimated_cost_usd: float | None = 0.05,
    include_metrics: bool = True,
) -> ExecutionResult:
    """Create a deterministic successful strategy execution."""

    completed_at = STARTED_AT + timedelta(
        seconds=duration_seconds,
    )

    context = Context()

    metrics = (
        StrategyExecutionMetrics(
            provider="test-provider",
            model="test-model",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=int(duration_seconds * 1000),
            estimated_cost_usd=estimated_cost_usd,
        )
        if include_metrics
        else None
    )

    return ExecutionResult(
        strategy_id=strategy_id,
        strategy_name="test-strategy",
        strategy_version="1.0.0",
        output="result",
        metrics=metrics,
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=completed_at,
    )


def create_successful_attempt(
    *,
    execution: ExecutionResult,
    attempt_number: int = 1,
) -> WorkflowStepAttempt:
    """Create a successful workflow step attempt."""

    return WorkflowStepAttempt(
        attempt_number=attempt_number,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        execution=execution,
    )


def create_failed_attempt(
    *,
    attempt_number: int = 1,
) -> WorkflowStepAttempt:
    """Create a failed workflow step attempt."""

    return WorkflowStepAttempt(
        attempt_number=attempt_number,
        started_at=STARTED_AT,
        completed_at=STARTED_AT
        + timedelta(
            milliseconds=100,
        ),
        failure=WorkflowStepFailure(
            exception_type="RuntimeError",
            message="Synthetic failure.",
        ),
    )


def create_executed_step(
    *,
    step_id: UUID = STEP_ID,
    strategy_id: UUID = STRATEGY_ID,
    duration_seconds: float = 5.0,
    estimated_cost_usd: float | None = 0.05,
    include_metrics: bool = True,
    attempts: tuple[WorkflowStepAttempt, ...] | None = None,
) -> WorkflowStepRun:
    """Create a deterministic executed workflow step."""

    execution = create_execution(
        strategy_id=strategy_id,
        duration_seconds=duration_seconds,
        estimated_cost_usd=estimated_cost_usd,
        include_metrics=include_metrics,
    )

    resolved_attempts = (
        attempts
        if attempts is not None
        else (
            create_successful_attempt(
                execution=execution,
            ),
        )
    )

    if resolved_attempts[-1].execution is None:
        resolved_attempts = (
            *resolved_attempts,
            create_successful_attempt(
                execution=execution,
                attempt_number=len(resolved_attempts) + 1,
            ),
        )

    return WorkflowStepRun(
        step_id=step_id,
        layer_index=0,
        status=WorkflowStepStatus.EXECUTED,
        execution=execution,
        attempts=resolved_attempts,
    )


def create_failed_step(
    *,
    step_id: UUID = STEP_ID,
) -> WorkflowStepRun:
    """Create a deterministic failed workflow step."""

    return WorkflowStepRun(
        step_id=step_id,
        layer_index=0,
        status=WorkflowStepStatus.FAILED,
        execution=None,
        attempts=(create_failed_attempt(),),
    )


def create_skipped_step(
    *,
    step_id: UUID = STEP_ID,
) -> WorkflowStepRun:
    """Create a deterministic skipped workflow step."""

    return WorkflowStepRun(
        step_id=step_id,
        layer_index=0,
        status=WorkflowStepStatus.SKIPPED,
        execution=None,
        attempts=(),
    )


def create_run(
    *,
    steps: tuple[WorkflowStepRun, ...] | None = None,
    duration_seconds: float = 5.0,
    estimated_cost_usd: float = 0.05,
) -> WorkflowRun:
    """Create a deterministic workflow run."""

    resolved_steps = (
        steps
        if steps is not None
        else (
            create_executed_step(
                duration_seconds=duration_seconds,
                estimated_cost_usd=estimated_cost_usd,
            ),
        )
    )

    return WorkflowRun(
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="test-workflow",
            description="Workflow used for scoring tests.",
        ),
        steps=resolved_steps,
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


def test_scoring_penalizes_success_after_retry() -> None:
    """A retried successful step should receive reduced reliability."""

    execution = create_execution()

    step = WorkflowStepRun(
        step_id=STEP_ID,
        layer_index=0,
        status=WorkflowStepStatus.EXECUTED,
        execution=execution,
        attempts=(
            create_failed_attempt(
                attempt_number=1,
            ),
            create_successful_attempt(
                execution=execution,
                attempt_number=2,
            ),
        ),
    )

    scorecard = WorkflowScorer(
        policy=create_policy(),
    ).score(
        run=create_run(
            steps=(step,),
        ),
        evaluation=create_evaluation(),
    )

    assert scorecard.reliability_score == pytest.approx(0.5)


def test_scoring_penalizes_failed_workflow_step() -> None:
    """A failed workflow step should reduce canonical reliability."""

    scorecard = WorkflowScorer(
        policy=create_policy(),
    ).score(
        run=create_run(
            steps=(create_failed_step(),),
        ),
        evaluation=create_evaluation(
            score=0.0,
        ),
    )

    assert scorecard.reliability_score == pytest.approx(0.25)


def test_scoring_penalizes_skipped_workflow_step() -> None:
    """A skipped workflow step should reduce completion reliability."""

    scorecard = WorkflowScorer(
        policy=create_policy(),
    ).score(
        run=create_run(
            steps=(create_skipped_step(),),
        ),
        evaluation=create_evaluation(),
    )

    assert scorecard.reliability_score == pytest.approx(0.5)


def test_scoring_sums_cost_across_executed_steps() -> None:
    """Workflow cost should include every successful step execution."""

    first_step = create_executed_step(
        step_id=STEP_ID,
        strategy_id=STRATEGY_ID,
        estimated_cost_usd=0.06,
    )

    second_step = create_executed_step(
        step_id=SECOND_STEP_ID,
        strategy_id=SECOND_STRATEGY_ID,
        estimated_cost_usd=0.04,
    )

    scorecard = WorkflowScorer(
        policy=WorkflowScoringPolicy(
            target_latency_seconds=10.0,
            target_cost_usd=0.05,
        ),
    ).score(
        run=create_run(
            steps=(
                first_step,
                second_step,
            ),
        ),
        evaluation=create_evaluation(),
    )

    assert scorecard.cost_score == pytest.approx(0.5)


def test_scoring_ignores_failed_and_skipped_steps_for_cost() -> None:
    """Steps without successful executions should not contribute cost."""

    successful_step = create_executed_step(
        step_id=STEP_ID,
        estimated_cost_usd=0.05,
    )

    scorecard = WorkflowScorer(
        policy=create_policy(),
    ).score(
        run=create_run(
            steps=(
                successful_step,
                create_failed_step(
                    step_id=SECOND_STEP_ID,
                ),
                create_skipped_step(
                    step_id=UUID("66666666-6666-6666-6666-666666666666"),
                ),
            ),
        ),
        evaluation=create_evaluation(),
    )

    assert scorecard.cost_score == pytest.approx(1.0)


def test_scoring_rejects_missing_execution_metrics() -> None:
    """Executed steps must provide cost evidence."""

    run = create_run(
        steps=(
            create_executed_step(
                include_metrics=False,
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match=("Executed workflow steps must provide estimated cost metrics for scoring."),
    ):
        WorkflowScorer(
            policy=create_policy(),
        ).score(
            run=run,
            evaluation=create_evaluation(),
        )


def test_scoring_rejects_missing_estimated_cost() -> None:
    """Execution metrics without cost data should not imply zero cost."""

    run = create_run(
        steps=(
            create_executed_step(
                estimated_cost_usd=None,
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match=("Executed workflow steps must provide estimated cost metrics for scoring."),
    ):
        WorkflowScorer(
            policy=create_policy(),
        ).score(
            run=run,
            evaluation=create_evaluation(),
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


def test_scoring_policy_is_immutable() -> None:
    """Workflow scoring policy should be durable and immutable."""

    policy = create_policy()

    with pytest.raises(ValidationError):
        policy.target_latency_seconds = 20.0

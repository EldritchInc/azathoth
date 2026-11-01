"""Tests for the span attributes built from Azathoth's records (ADR 0100)."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context
from azathoth.jobs import JobError, JobErrorCode, JobResult, JobStatus
from azathoth.strategies import StrategyExecutionMetrics
from azathoth.telemetry import ATTRIBUTE_KEYS, SPAN_NAMES
from azathoth.telemetry.attributes import (
    invocation_attributes,
    job_attributes,
    model_attributes,
    run_attributes,
    step_attributes,
)
from azathoth.telemetry.conventions import (
    INVOCATION_SPAN,
    JOB_SPAN,
    RUN_SPAN,
    STEP_SPAN,
)
from azathoth.workflows import (
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStepStatus,
)

STEP_ID = UUID("5f6a7b8c-9d0e-4f1a-8b2c-4d5e6f7a8b01")

WORKFLOW_ID = UUID("5f6a7b8c-9d0e-4f1a-8b2c-4d5e6f7a8b02")

RUN_ID = UUID("5f6a7b8c-9d0e-4f1a-8b2c-4d5e6f7a8b03")

INVOCATION_ID = UUID("5f6a7b8c-9d0e-4f1a-8b2c-4d5e6f7a8b04")

MOMENT = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

METRICS = StrategyExecutionMetrics(
    provider="openrouter",
    model="anthropic/claude-haiku",
    prompt_tokens=120,
    completion_tokens=30,
    total_tokens=150,
    latency_ms=640,
    estimated_cost_usd=0.000215,
)


def test_span_names_are_stable() -> None:
    assert (JOB_SPAN, INVOCATION_SPAN, RUN_SPAN, STEP_SPAN) == (
        "azathoth.job",
        "azathoth.invocation",
        "azathoth.run",
        "azathoth.step",
    )
    assert {JOB_SPAN, INVOCATION_SPAN, RUN_SPAN, STEP_SPAN} == SPAN_NAMES


def test_model_metrics_become_generative_ai_attributes() -> None:
    assert model_attributes(METRICS) == {
        "gen_ai.provider.name": "openrouter",
        "gen_ai.request.model": "anthropic/claude-haiku",
        "gen_ai.usage.input_tokens": 120,
        "gen_ai.usage.output_tokens": 30,
        "azathoth.cost.usd": 0.000215,
    }


def test_unknown_metrics_are_left_out() -> None:
    assert model_attributes(StrategyExecutionMetrics(latency_ms=3)) == {}
    assert model_attributes(None) == {}


def test_a_step_names_its_status_attempts_strategy_confidence_and_model() -> None:
    assert step_attributes(
        STEP_ID,
        WorkflowStepStatus.EXECUTED,
        attempts=2,
        strategy_name="Classify ticket cheaply [openrouter/anthropic/claude-haiku]",
        confidence=0.55,
        metrics=METRICS,
    ) == {
        "azathoth.step.id": str(STEP_ID),
        "azathoth.step.status": "executed",
        "azathoth.step.attempts": 2,
        "azathoth.strategy.name": "Classify ticket cheaply [openrouter/anthropic/claude-haiku]",
        "azathoth.step.confidence": 0.55,
        **model_attributes(METRICS),
    }


def test_a_skipped_step_names_only_its_status() -> None:
    assert step_attributes(STEP_ID, WorkflowStepStatus.SKIPPED, attempts=0) == {
        "azathoth.step.id": str(STEP_ID),
        "azathoth.step.status": "skipped",
        "azathoth.step.attempts": 0,
    }


def create_run(
    *,
    revision: int | None,
) -> WorkflowRun:
    """Create one run of a single skipped step."""

    return WorkflowRun(
        id=RUN_ID,
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="traced",
            description="Exercise run attributes.",
            version="1.0.0",
        ),
        workflow_revision=revision,
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.SKIPPED,
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=MOMENT,
        completed_at=MOMENT,
    )


def test_a_run_names_its_identity_status_and_step_counts() -> None:
    assert run_attributes(create_run(revision=3)) == {
        "azathoth.run.id": str(RUN_ID),
        "azathoth.workflow.id": str(WORKFLOW_ID),
        "azathoth.workflow.revision": 3,
        "azathoth.run.status": "succeeded",
        "azathoth.run.steps.executed": 0,
        "azathoth.run.steps.failed": 0,
        "azathoth.run.steps.skipped": 1,
    }


def test_a_run_without_a_revision_leaves_it_out() -> None:
    assert "azathoth.workflow.revision" not in run_attributes(create_run(revision=None))


def test_a_successful_invocation_names_its_outcome() -> None:
    assert invocation_attributes(
        ProductionInvocationSuccess(invocation_id=INVOCATION_ID, result={"secret": "x"}),
        workflow_id=WORKFLOW_ID,
    ) == {
        "azathoth.invocation.id": str(INVOCATION_ID),
        "azathoth.workflow.id": str(WORKFLOW_ID),
        "azathoth.invocation.outcome": "succeeded",
    }


def test_a_failed_invocation_names_its_code_and_never_its_message() -> None:
    attributes = invocation_attributes(
        ProductionInvocationFailure(
            invocation_id=INVOCATION_ID,
            error_code=ProductionInvocationErrorCode.TIMEOUT,
            message="Timed out reading Jane Doe's chart.",
        ),
        workflow_id=WORKFLOW_ID,
    )

    assert attributes == {
        "azathoth.invocation.id": str(INVOCATION_ID),
        "azathoth.workflow.id": str(WORKFLOW_ID),
        "azathoth.invocation.outcome": "timeout",
        "azathoth.error.code": "timeout",
    }


def test_a_job_names_its_kind_version_status_and_replay_but_never_its_key() -> None:
    attributes = job_attributes(
        JobResult(
            idempotency_key="patient-jane-doe-4711",
            status=JobStatus.SUCCEEDED,
            replayed=True,
            invocation_id=INVOCATION_ID,
            result={"diagnosis": "x"},
            error=None,
        )
    )

    assert attributes == {
        "azathoth.job.kind": "invoke",
        "azathoth.job.version": 1,
        "azathoth.job.status": "succeeded",
        "azathoth.job.replayed": True,
        "azathoth.invocation.id": str(INVOCATION_ID),
    }
    assert "jane" not in repr(attributes)


def test_a_rejected_job_names_its_code() -> None:
    attributes = job_attributes(
        JobResult(
            idempotency_key=None,
            status=JobStatus.REJECTED,
            invocation_id=None,
            error=JobError(code=JobErrorCode.INVALID_REQUEST, message="Bad 'ssn' field."),
        )
    )

    assert attributes == {
        "azathoth.job.kind": "invoke",
        "azathoth.job.version": 1,
        "azathoth.job.status": "rejected",
        "azathoth.job.replayed": False,
        "azathoth.error.code": "invalid_request",
    }


def test_every_builder_uses_only_documented_keys() -> None:
    built = {
        **model_attributes(METRICS),
        **step_attributes(
            STEP_ID,
            WorkflowStepStatus.EXECUTED,
            attempts=1,
            strategy_name="s",
            confidence=1.0,
            metrics=METRICS,
        ),
        **run_attributes(create_run(revision=1)),
        **invocation_attributes(
            ProductionInvocationFailure(
                invocation_id=INVOCATION_ID,
                error_code=ProductionInvocationErrorCode.TIMEOUT,
                message="m",
            ),
            workflow_id=WORKFLOW_ID,
        ),
        **job_attributes(
            JobResult(
                idempotency_key="k",
                status=JobStatus.REJECTED,
                invocation_id=None,
                error=JobError(code=JobErrorCode.INVALID_REQUEST, message="m"),
            )
        ),
    }

    assert set(built) <= ATTRIBUTE_KEYS

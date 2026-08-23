"""Tests for human-readable CLI execution rendering."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.cli import render_workflow_run
from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.strategies import StrategyExecutionMetrics
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRun,
    WorkflowStepAttempt,
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

RUN_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

STARTED_AT = datetime(
    2026,
    8,
    23,
    12,
    0,
    0,
    tzinfo=UTC,
)

COMPLETED_AT = datetime(
    2026,
    8,
    23,
    12,
    0,
    1,
    tzinfo=UTC,
)


def workflow_metadata() -> WorkflowMetadata:
    """Create deterministic workflow metadata."""

    return WorkflowMetadata(
        id=WORKFLOW_ID,
        name="rendered workflow",
        description=("Exercise human-readable workflow run rendering."),
        version="1.0.0",
    )


def successful_execution() -> ExecutionResult:
    """Create one successful execution result with complete metrics."""

    context = Context()

    return ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="rendered strategy",
        strategy_version="1.0.0",
        output={
            "result": "success",
        },
        metrics=StrategyExecutionMetrics(
            provider="openrouter",
            model="example/model",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=250,
            estimated_cost_usd=0.001234,
        ),
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def successful_run() -> WorkflowRun:
    """Create one deterministic successful workflow run."""

    execution = successful_execution()

    attempt = WorkflowStepAttempt(
        attempt_number=1,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        execution=execution,
    )

    return WorkflowRun(
        id=RUN_ID,
        workflow=workflow_metadata(),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.EXECUTED,
                execution=execution,
                attempts=(attempt,),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def failed_run() -> WorkflowRun:
    """Create one deterministic failed workflow run."""

    attempt = WorkflowStepAttempt(
        attempt_number=1,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        failure=WorkflowStepFailure(
            exception_type="RuntimeError",
            message="The eldritch machine rejected reality.",
        ),
    )

    return WorkflowRun(
        id=RUN_ID,
        workflow=workflow_metadata(),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.FAILED,
                attempts=(attempt,),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def test_workflow_run_rendering_includes_identity_and_status() -> None:
    rendered = render_workflow_run(successful_run())

    assert "Workflow: rendered workflow\n" in rendered
    assert f"Workflow ID: {WORKFLOW_ID}\n" in rendered
    assert f"Run ID: {RUN_ID}\n" in rendered
    assert "Status: succeeded\n" in rendered
    assert "Duration: 1.000s\n" in rendered


def test_workflow_run_rendering_includes_statistics() -> None:
    rendered = render_workflow_run(successful_run())

    assert "Steps: 1\n" in rendered
    assert "Executed: 1\n" in rendered
    assert "Failed: 0\n" in rendered
    assert "Skipped: 0\n" in rendered
    assert "Retries: 0\n" in rendered


def test_workflow_run_rendering_includes_step_execution() -> None:
    rendered = render_workflow_run(successful_run())

    assert "Step 1\n" in rendered
    assert f"ID: {STEP_ID}\n" in rendered
    assert "Status: executed\n" in rendered
    assert "Attempts: 1\n" in rendered
    assert "Strategy: rendered strategy\n" in rendered


def test_workflow_run_rendering_includes_execution_metrics() -> None:
    rendered = render_workflow_run(successful_run())

    assert "Provider: openrouter\n" in rendered
    assert "Model: example/model\n" in rendered
    assert "Prompt Tokens: 10\n" in rendered
    assert "Completion Tokens: 5\n" in rendered
    assert "Total Tokens: 15\n" in rendered
    assert "Latency: 250 ms\n" in rendered
    assert "Estimated Cost: $0.001234\n" in rendered


def test_workflow_run_rendering_uses_json_for_structured_output() -> None:
    rendered = render_workflow_run(successful_run())

    assert 'Output:\n{\n  "result": "success"\n}' in rendered


def test_workflow_run_rendering_omits_absent_metrics() -> None:
    context = Context()

    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="no metrics",
        strategy_version="1.0.0",
        output="success",
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    attempt = WorkflowStepAttempt(
        attempt_number=1,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        execution=execution,
    )

    run = WorkflowRun(
        id=RUN_ID,
        workflow=workflow_metadata(),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                execution=execution,
                attempts=(attempt,),
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    rendered = render_workflow_run(run)

    assert "Strategy: no metrics\n" in rendered
    assert "Provider:" not in rendered
    assert "Model:" not in rendered
    assert "Total Tokens:" not in rendered
    assert "Estimated Cost:" not in rendered

    assert 'Output:\n"success"' in rendered


def test_workflow_run_rendering_includes_failed_step_evidence() -> None:
    rendered = render_workflow_run(failed_run())

    assert "Status: failed\n" in rendered
    assert "Failed: 1\n" in rendered

    assert f"ID: {STEP_ID}\n" in rendered
    assert "Status: failed\n" in rendered
    assert "Attempts: 1\n" in rendered

    assert "Error: RuntimeError: The eldritch machine rejected reality." in rendered

"""Tests for one-line workflow run summary rendering."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from azathoth.cli import (
    WorkflowRunSource,
    render_workflow_run_summaries,
)
from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunFeedbackDisposition,
    WorkflowStepAttempt,
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

SECOND_RUN_ID = UUID("99999999-9999-4999-8999-999999999992")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

STARTED_AT = datetime(
    2026,
    10,
    2,
    12,
    0,
    0,
    tzinfo=UTC,
)


def workflow_metadata() -> WorkflowMetadata:
    """Create deterministic workflow metadata."""

    return WorkflowMetadata(
        id=WORKFLOW_ID,
        name="summarized workflow",
        description="Exercise run summary rendering.",
        version="1.0.0",
    )


def successful_run(
    run_id: UUID,
    *,
    started_at: datetime = STARTED_AT,
    duration: timedelta = timedelta(milliseconds=1500),
) -> WorkflowRun:
    """Create one successful single-step run."""

    context = Context()
    completed_at = started_at + duration

    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="summary strategy",
        strategy_version="1.0.0",
        output="success",
        initial_context=context,
        final_context=context,
        started_at=started_at,
        completed_at=completed_at,
    )

    return WorkflowRun(
        id=run_id,
        workflow=workflow_metadata(),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.EXECUTED,
                execution=execution,
                attempts=(
                    WorkflowStepAttempt(
                        attempt_number=1,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution=execution,
                    ),
                ),
            ),
        ),
        initial_context=context,
        final_context=context,
        started_at=started_at,
        completed_at=completed_at,
    )


def failed_run(
    run_id: UUID,
) -> WorkflowRun:
    """Create one failed single-step run."""

    completed_at = STARTED_AT + timedelta(milliseconds=250)

    return WorkflowRun(
        id=run_id,
        workflow=workflow_metadata(),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.FAILED,
                attempts=(
                    WorkflowStepAttempt(
                        attempt_number=1,
                        started_at=STARTED_AT,
                        completed_at=completed_at,
                        failure=WorkflowStepFailure(
                            exception_type="RuntimeError",
                            message="Summary failure.",
                        ),
                    ),
                ),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=completed_at,
    )


def test_summary_renders_configured_successful_run() -> None:
    rendered = render_workflow_run_summaries(
        (successful_run(FIRST_RUN_ID),),
        run_sources={},
        latest_dispositions={},
    )

    assert rendered == (
        f"{FIRST_RUN_ID}  2026-10-02T12:00:00+00:00  succeeded  1.500s  configured  -"
    )


def test_summary_renders_production_failed_run_with_aligned_status() -> None:
    rendered = render_workflow_run_summaries(
        (failed_run(FIRST_RUN_ID),),
        run_sources={
            FIRST_RUN_ID: WorkflowRunSource.PRODUCTION,
        },
        latest_dispositions={},
    )

    assert rendered == (
        f"{FIRST_RUN_ID}  2026-10-02T12:00:00+00:00  failed     0.250s  production  -"
    )


def test_summary_renders_experiment_run() -> None:
    rendered = render_workflow_run_summaries(
        (successful_run(FIRST_RUN_ID),),
        run_sources={
            FIRST_RUN_ID: WorkflowRunSource.EXPERIMENT,
        },
        latest_dispositions={},
    )

    assert rendered == (
        f"{FIRST_RUN_ID}  2026-10-02T12:00:00+00:00  succeeded  1.500s  experiment  -"
    )


def test_summary_preserves_given_order_one_line_per_run() -> None:
    rendered = render_workflow_run_summaries(
        (
            successful_run(
                SECOND_RUN_ID,
                started_at=STARTED_AT + timedelta(minutes=5),
            ),
            successful_run(FIRST_RUN_ID),
        ),
        run_sources={
            SECOND_RUN_ID: WorkflowRunSource.PRODUCTION,
        },
        latest_dispositions={},
    )

    lines = rendered.splitlines()

    assert len(lines) == 2
    assert lines[0].startswith(f"{SECOND_RUN_ID}  2026-10-02T12:05:00+00:00")
    assert lines[0].endswith("production  -")
    assert lines[1].startswith(f"{FIRST_RUN_ID}  2026-10-02T12:00:00+00:00")
    assert lines[1].endswith("configured  -")


def test_summary_of_no_runs_is_empty() -> None:
    assert (
        render_workflow_run_summaries(
            (),
            run_sources={},
            latest_dispositions={},
        )
        == ""
    )


def test_summary_renders_latest_disposition_per_run() -> None:
    rendered = render_workflow_run_summaries(
        (
            successful_run(SECOND_RUN_ID),
            failed_run(FIRST_RUN_ID),
        ),
        run_sources={},
        latest_dispositions={
            SECOND_RUN_ID: WorkflowRunFeedbackDisposition.GOOD,
            FIRST_RUN_ID: WorkflowRunFeedbackDisposition.BAD,
        },
    )

    assert rendered.splitlines() == [
        f"{SECOND_RUN_ID}  2026-10-02T12:00:00+00:00  succeeded  1.500s  configured  good",
        f"{FIRST_RUN_ID}  2026-10-02T12:00:00+00:00  failed     0.250s  configured  bad",
    ]

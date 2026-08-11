"""Tests for workflow execution summary properties."""

from azathoth.context import Context
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStepStatus,
)

from .test_statistics_computation import (
    COMPLETED_AT,
    STARTED_AT,
    STEP_ONE_ID,
    WORKFLOW_ID,
    create_failed_attempt,
    create_run,
)


def test_workflow_reports_success() -> None:
    run = create_run()

    assert run.succeeded
    assert not run.failed


def test_workflow_reports_duration() -> None:
    run = create_run()

    assert run.duration_seconds == 5.0


def test_workflow_reports_retry_count() -> None:
    run = create_run()

    assert run.retry_count == 2


def test_workflow_reports_step_counts() -> None:
    run = create_run()

    assert run.executed_step_count == 2
    assert run.failed_step_count == 0
    assert run.skipped_step_count == 1


def test_workflow_reports_attempt_count() -> None:
    run = create_run()

    assert run.total_attempt_count == 4


def test_failed_workflow_reports_failure() -> None:
    run = WorkflowRun(
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Failure",
            description="Failure",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ONE_ID,
                layer_index=0,
                status=WorkflowStepStatus.FAILED,
                execution=None,
                attempts=(
                    create_failed_attempt(
                        attempt_number=1,
                    ),
                ),
                values=(),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    assert run.failed
    assert not run.succeeded

    assert run.failed_step_count == 1
    assert run.executed_step_count == 0

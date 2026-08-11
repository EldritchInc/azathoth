"""Tests for reliability metrics when no workflow steps are attempted."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("20d322d4-4020-47de-80de-136a31d36f41")
STEP_ID = UUID("a78af7b4-5824-4b93-b4e7-a57dc80f952d")

TIMESTAMP = datetime(
    2026,
    8,
    11,
    14,
    15,
    tzinfo=UTC,
)


def test_all_skipped_workflow_has_defined_reliability_metrics() -> None:
    run = WorkflowRun(
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Skipped workflow",
            description="No workflow steps execute.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.SKIPPED,
                execution=None,
                attempts=(),
                values=(),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=TIMESTAMP,
        completed_at=TIMESTAMP,
    )

    metrics = run.reliability

    assert metrics.completion_rate == 0.0
    assert metrics.first_attempt_success_rate == 0.0
    assert metrics.retry_rate == 0.0
    assert metrics.failure_rate == 0.0

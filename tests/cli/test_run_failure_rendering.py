"""Tests for rendering run-failure evaluations in `run show`."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from azathoth.cli import render_workflow_run_evaluations
from azathoth.context import Context
from azathoth.evaluation import (
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunEvaluation,
    WorkflowStepAttempt,
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepStatus,
    evaluate_failed_run,
)

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

STEP_ID = UUID("88888888-8888-4888-8888-888888888881")

EVALUATION_ID = UUID("dddddddd-dddd-4ddd-8ddd-ddddddddddd1")

STARTED_AT = datetime(
    2026,
    10,
    22,
    12,
    0,
    tzinfo=UTC,
)

EVALUATED_AT = datetime(
    2026,
    10,
    22,
    12,
    5,
    tzinfo=UTC,
)


def create_failed_run() -> WorkflowRun:
    """Create a run whose only step failed."""

    return WorkflowRun(
        id=RUN_ID,
        workflow=WorkflowMetadata(
            name="Failing workflow",
            description="A workflow whose only step fails.",
        ),
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                status=WorkflowStepStatus.FAILED,
                attempts=(
                    WorkflowStepAttempt(
                        attempt_number=1,
                        started_at=STARTED_AT,
                        completed_at=STARTED_AT
                        + timedelta(
                            milliseconds=100,
                        ),
                        failure=WorkflowStepFailure(
                            exception_type="RuntimeError",
                            message="Provider unavailable.",
                        ),
                    ),
                ),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=STARTED_AT
        + timedelta(
            seconds=1,
        ),
    )


def test_render_run_failure_evaluation() -> None:
    """A run-failure evaluation renders like any other evaluation."""

    evaluation = evaluate_failed_run(
        create_failed_run(),
        ExpectedOutcome(
            description="The answer token.",
            value="AZATHOTH",
            comparison=OutcomeComparison.EXACT,
        ),
    ).model_copy(
        update={
            "id": EVALUATION_ID,
        },
    )

    rendered = render_workflow_run_evaluations(
        (
            WorkflowRunEvaluation(
                run_id=RUN_ID,
                evaluation=evaluation,
                evaluated_at=EVALUATED_AT,
            ),
        )
    )

    assert rendered == "\n".join(
        (
            "Evaluations: 1",
            "",
            "Evaluation 1",
            f"ID: {EVALUATION_ID}",
            "Evaluated: 2026-10-22T12:05:00+00:00",
            "Evaluator: workflow-run-failure 1.0.0",
            "Status: failed",
            "Score: 0.000000 (threshold 1.000000)",
            f"Reason: Workflow run failed at step {STEP_ID}: Provider unavailable.",
            'Evidence: expected = "AZATHOTH"',
            f'Evidence: failed_step_id = "{STEP_ID}"',
            'Evidence: failure = {"exception_type": "RuntimeError", '
            '"message": "Provider unavailable."}',
        )
    )

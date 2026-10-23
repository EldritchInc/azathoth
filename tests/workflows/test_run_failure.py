"""Tests for the evaluation recorded for failed workflow runs."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    EvaluationStatus,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.workflows import (
    RUN_FAILURE_EVALUATOR_NAME,
    RUN_FAILURE_EVALUATOR_VERSION,
    SQLiteWorkflowRunEvaluationRepository,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunEvaluation,
    WorkflowStepAttempt,
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepStatus,
    evaluate_failed_run,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

THIRD_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

RUN_ID = UUID("55555555-5555-5555-5555-555555555555")

STARTED_AT = datetime(
    2026,
    10,
    22,
    12,
    0,
    tzinfo=UTC,
)


def create_expected() -> ExpectedOutcome:
    """Create a deterministic expected outcome."""

    return ExpectedOutcome(
        description="The answer token.",
        value={"token": "AZATHOTH"},
        comparison=OutcomeComparison.EXACT,
    )


def create_failed_attempt(
    *,
    attempt_number: int = 1,
    exception_type: str = "RuntimeError",
    message: str = "Provider unavailable.",
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
            exception_type=exception_type,
            message=message,
        ),
    )


def create_failed_step(
    *,
    step_id: UUID,
    layer_index: int = 0,
    attempts: tuple[WorkflowStepAttempt, ...] | None = None,
) -> WorkflowStepRun:
    """Create a failed workflow step."""

    return WorkflowStepRun(
        step_id=step_id,
        layer_index=layer_index,
        status=WorkflowStepStatus.FAILED,
        attempts=(attempts if attempts is not None else (create_failed_attempt(),)),
    )


def create_skipped_step(
    *,
    step_id: UUID,
    layer_index: int = 0,
) -> WorkflowStepRun:
    """Create a skipped workflow step."""

    return WorkflowStepRun(
        step_id=step_id,
        layer_index=layer_index,
        status=WorkflowStepStatus.SKIPPED,
    )


def create_run(
    *steps: WorkflowStepRun,
) -> WorkflowRun:
    """Create a deterministic workflow run from recorded steps."""

    return WorkflowRun(
        id=RUN_ID,
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Failing workflow",
            description="A workflow whose steps fail.",
        ),
        steps=steps,
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=STARTED_AT
        + timedelta(
            seconds=1,
        ),
    )


def test_failed_run_evaluation_always_fails() -> None:
    """A failed run scores zero and fails under the run-failure evaluator."""

    evaluation = evaluate_failed_run(
        create_run(
            create_failed_step(
                step_id=FIRST_STEP_ID,
            ),
        ),
        create_expected(),
    )

    assert evaluation.evaluator_name == "workflow-run-failure"
    assert evaluation.evaluator_name == RUN_FAILURE_EVALUATOR_NAME
    assert evaluation.evaluator_version == "1.0.0"
    assert evaluation.evaluator_version == RUN_FAILURE_EVALUATOR_VERSION
    assert evaluation.score == 0.0
    assert evaluation.threshold == 1.0
    assert evaluation.status is EvaluationStatus.FAILED
    assert not evaluation.passed


def test_failed_run_evaluation_names_failed_step_and_message() -> None:
    """The reason names the failed step and its failure message."""

    evaluation = evaluate_failed_run(
        create_run(
            create_failed_step(
                step_id=FIRST_STEP_ID,
            ),
        ),
        create_expected(),
    )

    assert evaluation.reason == (
        f"Workflow run failed at step {FIRST_STEP_ID}: Provider unavailable."
    )


def test_failed_run_evaluation_records_evidence() -> None:
    """Evidence lists the expected value, failed step, and failure."""

    evaluation = evaluate_failed_run(
        create_run(
            create_failed_step(
                step_id=FIRST_STEP_ID,
                attempts=(
                    create_failed_attempt(
                        exception_type="TimeoutError",
                        message="Model call timed out.",
                    ),
                ),
            ),
        ),
        create_expected(),
    )

    assert tuple((item.label, item.value) for item in evaluation.evidence) == (
        (
            "expected",
            {"token": "AZATHOTH"},
        ),
        (
            "failed_step_id",
            str(FIRST_STEP_ID),
        ),
        (
            "failure",
            {
                "exception_type": "TimeoutError",
                "message": "Model call timed out.",
            },
        ),
    )


def test_failed_run_evaluation_blames_first_failed_step() -> None:
    """With several failed steps, the first in recorded order is blamed."""

    evaluation = evaluate_failed_run(
        create_run(
            create_skipped_step(
                step_id=FIRST_STEP_ID,
            ),
            create_failed_step(
                step_id=SECOND_STEP_ID,
                attempts=(
                    create_failed_attempt(
                        message="First failure.",
                    ),
                ),
            ),
            create_failed_step(
                step_id=THIRD_STEP_ID,
                layer_index=1,
                attempts=(
                    create_failed_attempt(
                        message="Second failure.",
                    ),
                ),
            ),
        ),
        create_expected(),
    )

    assert evaluation.reason == (f"Workflow run failed at step {SECOND_STEP_ID}: First failure.")


def test_failed_run_evaluation_uses_final_attempt_failure() -> None:
    """A retried step is blamed with the failure of its final attempt."""

    evaluation = evaluate_failed_run(
        create_run(
            create_failed_step(
                step_id=FIRST_STEP_ID,
                attempts=(
                    create_failed_attempt(
                        attempt_number=1,
                        message="Transient failure.",
                    ),
                    create_failed_attempt(
                        attempt_number=2,
                        message="Retries exhausted.",
                    ),
                ),
            ),
        ),
        create_expected(),
    )

    assert evaluation.reason == (f"Workflow run failed at step {FIRST_STEP_ID}: Retries exhausted.")


def test_failed_run_evaluation_rejects_run_without_failed_step() -> None:
    """A run with no failed step cannot be judged as a failure."""

    with pytest.raises(
        ValueError,
    ) as error:
        evaluate_failed_run(
            create_run(
                create_skipped_step(
                    step_id=FIRST_STEP_ID,
                ),
            ),
            create_expected(),
        )

    assert str(error.value) == f"Workflow run {RUN_ID} did not fail."


def test_failed_run_evaluation_persists_like_any_evaluation(
    tmp_path: Path,
) -> None:
    """The failure evaluation round-trips through the SQLite repository."""

    evaluation = evaluate_failed_run(
        create_run(
            create_failed_step(
                step_id=FIRST_STEP_ID,
            ),
        ),
        create_expected(),
    )

    database = tmp_path / "azathoth.db"

    SQLiteWorkflowRunEvaluationRepository(database).save(
        WorkflowRunEvaluation(
            run_id=RUN_ID,
            evaluation=evaluation,
        )
    )

    restored = SQLiteWorkflowRunEvaluationRepository(database).evaluations_for_run(
        RUN_ID,
    )

    assert tuple(record.evaluation for record in restored) == (evaluation,)

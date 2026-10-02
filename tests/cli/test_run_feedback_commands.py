"""Tests for recording workflow run feedback."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    record_run_feedback,
)
from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows import (
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunFeedbackDisposition,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

UNKNOWN_RUN_ID = UUID("99999999-9999-4999-8999-999999999999")

STARTED_AT = datetime(
    2026,
    10,
    2,
    12,
    0,
    tzinfo=UTC,
)


def configure_judged_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Persist one judgeable run in an isolated durable database."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    context = Context()
    completed_at = STARTED_AT + timedelta(seconds=1)

    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="Judged prompt",
        strategy_version="1.0.0",
        output="positive",
        initial_context=context,
        final_context=context,
        started_at=STARTED_AT,
        completed_at=completed_at,
    )

    SQLiteWorkflowRunRepository(database).save(
        WorkflowRun(
            id=RUN_ID,
            workflow=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="judged workflow",
                description="Workflow used to test feedback recording.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepRun(
                    step_id=STEP_ID,
                    layer_index=0,
                    status=WorkflowStepStatus.EXECUTED,
                    execution=execution,
                    attempts=(
                        WorkflowStepAttempt(
                            attempt_number=1,
                            started_at=STARTED_AT,
                            completed_at=completed_at,
                            execution=execution,
                        ),
                    ),
                ),
            ),
            initial_context=context,
            final_context=context,
            started_at=STARTED_AT,
            completed_at=completed_at,
        )
    )

    return database


def test_record_good_feedback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_judged_run(
        monkeypatch,
        tmp_path,
    )

    result = record_run_feedback(
        RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
    )

    captured = capsys.readouterr()

    feedback = SQLiteWorkflowRunFeedbackRepository(database).feedback_for_run(RUN_ID)

    assert result == 0
    assert captured.err == ""
    assert len(feedback) == 1
    assert feedback[0].disposition is WorkflowRunFeedbackDisposition.GOOD
    assert feedback[0].reason is None
    assert feedback[0].corrected_output is None
    assert captured.out == f"Recorded good feedback {feedback[0].id} for run {RUN_ID}.\n"


def test_record_bad_feedback_with_reason_and_corrected_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_judged_run(
        monkeypatch,
        tmp_path,
    )

    result = record_run_feedback(
        RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason="  Complaint labeled as praise.  ",
        corrected_output={
            "classification": "negative",
        },
    )

    captured = capsys.readouterr()

    feedback = SQLiteWorkflowRunFeedbackRepository(database).feedback_for_run(RUN_ID)

    assert result == 0
    assert captured.err == ""
    assert len(feedback) == 1
    assert feedback[0].disposition is WorkflowRunFeedbackDisposition.BAD
    assert feedback[0].reason == "Complaint labeled as praise."
    assert feedback[0].corrected_output == {
        "classification": "negative",
    }
    assert captured.out == f"Recorded bad feedback {feedback[0].id} for run {RUN_ID}.\n"


def test_record_good_feedback_treats_blank_reason_as_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = configure_judged_run(
        monkeypatch,
        tmp_path,
    )

    result = record_run_feedback(
        RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
        reason="   ",
    )

    feedback = SQLiteWorkflowRunFeedbackRepository(database).feedback_for_run(RUN_ID)

    assert result == 0
    assert feedback[0].reason is None


def test_record_feedback_rejects_unknown_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_judged_run(
        monkeypatch,
        tmp_path,
    )

    result = record_run_feedback(
        UNKNOWN_RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Run {UNKNOWN_RUN_ID} was not found.\n"
    assert SQLiteWorkflowRunFeedbackRepository(database).feedback() == ()


@pytest.mark.parametrize(
    "reason",
    (
        None,
        "",
        "   ",
    ),
)
def test_record_bad_feedback_requires_reason(
    reason: str | None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_judged_run(
        monkeypatch,
        tmp_path,
    )

    result = record_run_feedback(
        RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason=reason,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "Bad workflow run feedback requires a reason.\n"
    assert SQLiteWorkflowRunFeedbackRepository(database).feedback() == ()


def test_record_good_feedback_rejects_corrected_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_judged_run(
        monkeypatch,
        tmp_path,
    )

    result = record_run_feedback(
        RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
        corrected_output="negative",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "A corrected output can only accompany bad feedback.\n"
    assert SQLiteWorkflowRunFeedbackRepository(database).feedback() == ()

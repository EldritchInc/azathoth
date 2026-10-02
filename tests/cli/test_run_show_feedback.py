"""Tests for feedback in persisted run inspection."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    show_run,
)
from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.workflows import (
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
    WorkflowStepAttempt,
    WorkflowStepRun,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

OTHER_RUN_ID = UUID("99999999-9999-4999-8999-999999999992")

FIRST_FEEDBACK_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1")

SECOND_FEEDBACK_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2")

OTHER_FEEDBACK_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee3")

STARTED_AT = datetime(
    2026,
    10,
    2,
    12,
    0,
    tzinfo=UTC,
)


def configure_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at an isolated durable database."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    return database


def create_run(
    run_id: UUID,
) -> WorkflowRun:
    """Create one successful single-step run."""

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

    return WorkflowRun(
        id=run_id,
        workflow=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="judged workflow",
            description="Workflow used to test feedback inspection.",
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


def save_runs(
    database: Path,
) -> None:
    """Persist the judged run and one unrelated run."""

    repository = SQLiteWorkflowRunRepository(database)

    repository.save(create_run(RUN_ID))
    repository.save(create_run(OTHER_RUN_ID))


def test_show_run_reports_absent_feedback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_runs(database)

    result = show_run(RUN_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert captured.out.endswith('"positive"\n\nFeedback: none\n')


def test_show_run_appends_feedback_for_that_run_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_runs(database)

    feedback_repository = SQLiteWorkflowRunFeedbackRepository(database)

    feedback_repository.save(
        WorkflowRunFeedback(
            id=FIRST_FEEDBACK_ID,
            run_id=RUN_ID,
            disposition=WorkflowRunFeedbackDisposition.BAD,
            reason="Complaint labeled as praise.",
            corrected_output="negative",
            created_at=STARTED_AT + timedelta(minutes=1),
        )
    )
    feedback_repository.save(
        WorkflowRunFeedback(
            id=OTHER_FEEDBACK_ID,
            run_id=OTHER_RUN_ID,
            disposition=WorkflowRunFeedbackDisposition.GOOD,
            created_at=STARTED_AT + timedelta(minutes=2),
        )
    )
    feedback_repository.save(
        WorkflowRunFeedback(
            id=SECOND_FEEDBACK_ID,
            run_id=RUN_ID,
            disposition=WorkflowRunFeedbackDisposition.GOOD,
            reason="Second reviewer disagrees.",
            created_at=STARTED_AT + timedelta(minutes=3),
        )
    )

    result = show_run(RUN_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    lines = captured.out.splitlines()

    assert "Feedback: 2" in lines
    assert lines.index("Feedback: 2") > lines.index(f"Run ID: {RUN_ID}")
    assert lines.index(f"ID: {FIRST_FEEDBACK_ID}") < lines.index(f"ID: {SECOND_FEEDBACK_ID}")
    assert "Reason: Complaint labeled as praise." in lines
    assert "Corrected Output:" in lines
    assert f"ID: {OTHER_FEEDBACK_ID}" not in lines

"""Tests for evaluator judgments in persisted run inspection."""

from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import show_run
from azathoth.evaluation import (
    EvaluationResult,
    EvaluationStatus,
)
from azathoth.workflows import (
    SQLiteWorkflowRunEvaluationRepository,
    SQLiteWorkflowRunFeedbackRepository,
    WorkflowRunEvaluation,
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
)
from tests.cli.test_run_show_feedback import (
    FIRST_FEEDBACK_ID,
    OTHER_RUN_ID,
    RUN_ID,
    STARTED_AT,
    configure_database,
    save_runs,
)

FIRST_EVALUATION_ID = UUID("dddddddd-dddd-4ddd-8ddd-ddddddddddd1")

SECOND_EVALUATION_ID = UUID("dddddddd-dddd-4ddd-8ddd-ddddddddddd2")

OTHER_EVALUATION_ID = UUID("dddddddd-dddd-4ddd-8ddd-ddddddddddd3")


def create_evaluation(
    evaluation_id: UUID,
    *,
    run_id: UUID,
    passed: bool,
) -> WorkflowRunEvaluation:
    """Create one evaluator judgment of one run."""

    return WorkflowRunEvaluation(
        run_id=run_id,
        evaluation=EvaluationResult(
            id=evaluation_id,
            evaluator_name="exact-match",
            evaluator_version="2.0.0",
            score=1.0 if passed else 0.0,
            status=EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED,
            reason="Judged by test.",
        ),
        evaluated_at=STARTED_AT + timedelta(minutes=1),
    )


def test_show_run_reports_absent_evaluations_before_feedback(
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
    assert captured.out.endswith('"positive"\n\nEvaluations: none\n\nFeedback: none\n')


def test_show_run_appends_evaluations_for_that_run_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_runs(database)

    evaluations = SQLiteWorkflowRunEvaluationRepository(database)

    evaluations.save(create_evaluation(FIRST_EVALUATION_ID, run_id=RUN_ID, passed=False))
    evaluations.save(create_evaluation(OTHER_EVALUATION_ID, run_id=OTHER_RUN_ID, passed=True))
    evaluations.save(create_evaluation(SECOND_EVALUATION_ID, run_id=RUN_ID, passed=True))

    SQLiteWorkflowRunFeedbackRepository(database).save(
        WorkflowRunFeedback(
            id=FIRST_FEEDBACK_ID,
            run_id=RUN_ID,
            disposition=WorkflowRunFeedbackDisposition.GOOD,
            created_at=STARTED_AT + timedelta(minutes=2),
        )
    )

    result = show_run(RUN_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    lines = captured.out.splitlines()

    assert lines.index(f"Run ID: {RUN_ID}") < lines.index("Evaluations: 2")
    assert lines.index("Evaluations: 2") < lines.index("Feedback: 1")
    assert lines.index(f"ID: {FIRST_EVALUATION_ID}") < lines.index(f"ID: {SECOND_EVALUATION_ID}")
    assert "Status: failed" in lines
    assert "Status: passed" in lines
    assert f"ID: {OTHER_EVALUATION_ID}" not in lines

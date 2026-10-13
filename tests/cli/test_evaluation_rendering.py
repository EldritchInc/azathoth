"""Tests for human-readable workflow run evaluation rendering."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.cli import render_workflow_run_evaluations
from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
)
from azathoth.workflows import WorkflowRunEvaluation

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

FIRST_EVALUATION_ID = UUID("dddddddd-dddd-4ddd-8ddd-ddddddddddd1")

SECOND_EVALUATION_ID = UUID("dddddddd-dddd-4ddd-8ddd-ddddddddddd2")

EVALUATED_AT = datetime(
    2026,
    10,
    2,
    12,
    5,
    tzinfo=UTC,
)


def test_render_no_evaluations() -> None:
    assert render_workflow_run_evaluations(()) == "Evaluations: none"


def test_render_evaluations_in_given_order_with_compact_evidence() -> None:
    rendered = render_workflow_run_evaluations(
        (
            WorkflowRunEvaluation(
                run_id=RUN_ID,
                evaluation=EvaluationResult(
                    id=FIRST_EVALUATION_ID,
                    evaluator_name="exact-match",
                    evaluator_version="2.0.0",
                    score=0.0,
                    threshold=1.0,
                    status=EvaluationStatus.FAILED,
                    reason="Actual value did not exactly match expected value at $.intent.",
                    evidence=(
                        EvaluationEvidence(
                            label="expected",
                            value={"intent": "refund"},
                        ),
                        EvaluationEvidence(
                            label="actual",
                            value={"intent": "Ünknown"},
                        ),
                        EvaluationEvidence(
                            label="difference_path",
                            value="$.intent",
                        ),
                    ),
                ),
                evaluated_at=EVALUATED_AT,
            ),
            WorkflowRunEvaluation(
                run_id=RUN_ID,
                evaluation=EvaluationResult(
                    id=SECOND_EVALUATION_ID,
                    evaluator_name="normalized-match",
                    evaluator_version="1.0.0",
                    score=1.0,
                    threshold=1.0,
                    status=EvaluationStatus.PASSED,
                    reason="Actual value matched expected value after normalization.",
                ),
                evaluated_at=EVALUATED_AT,
            ),
        )
    )

    assert rendered == "\n".join(
        (
            "Evaluations: 2",
            "",
            "Evaluation 1",
            f"ID: {FIRST_EVALUATION_ID}",
            "Evaluated: 2026-10-02T12:05:00+00:00",
            "Evaluator: exact-match 2.0.0",
            "Status: failed",
            "Score: 0.000000 (threshold 1.000000)",
            "Reason: Actual value did not exactly match expected value at $.intent.",
            'Evidence: expected = {"intent": "refund"}',
            'Evidence: actual = {"intent": "Ünknown"}',
            'Evidence: difference_path = "$.intent"',
            "",
            "Evaluation 2",
            f"ID: {SECOND_EVALUATION_ID}",
            "Evaluated: 2026-10-02T12:05:00+00:00",
            "Evaluator: normalized-match 1.0.0",
            "Status: passed",
            "Score: 1.000000 (threshold 1.000000)",
            "Reason: Actual value matched expected value after normalization.",
        )
    )

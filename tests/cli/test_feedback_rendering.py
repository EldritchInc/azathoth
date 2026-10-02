"""Tests for human-readable workflow run feedback rendering."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.cli import render_workflow_run_feedback
from azathoth.workflows import (
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
)

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")

FIRST_FEEDBACK_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1")

SECOND_FEEDBACK_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2")

FIRST_CREATED_AT = datetime(
    2026,
    10,
    2,
    12,
    0,
    tzinfo=UTC,
)

SECOND_CREATED_AT = datetime(
    2026,
    10,
    2,
    13,
    30,
    tzinfo=UTC,
)


def test_render_without_feedback() -> None:
    assert render_workflow_run_feedback(()) == "Feedback: none"


def test_render_good_feedback_without_optional_fields() -> None:
    rendered = render_workflow_run_feedback(
        (
            WorkflowRunFeedback(
                id=FIRST_FEEDBACK_ID,
                run_id=RUN_ID,
                disposition=WorkflowRunFeedbackDisposition.GOOD,
                created_at=FIRST_CREATED_AT,
            ),
        )
    )

    assert rendered == "\n".join(
        (
            "Feedback: 1",
            "",
            "Feedback 1",
            f"ID: {FIRST_FEEDBACK_ID}",
            "Created: 2026-10-02T12:00:00+00:00",
            "Disposition: good",
        )
    )


def test_render_bad_feedback_with_reason_and_corrected_output() -> None:
    rendered = render_workflow_run_feedback(
        (
            WorkflowRunFeedback(
                id=FIRST_FEEDBACK_ID,
                run_id=RUN_ID,
                disposition=WorkflowRunFeedbackDisposition.BAD,
                reason="Classified a complaint as praise.",
                corrected_output={
                    "classification": "negative",
                },
                created_at=FIRST_CREATED_AT,
            ),
        )
    )

    assert rendered == "\n".join(
        (
            "Feedback: 1",
            "",
            "Feedback 1",
            f"ID: {FIRST_FEEDBACK_ID}",
            "Created: 2026-10-02T12:00:00+00:00",
            "Disposition: bad",
            "Reason: Classified a complaint as praise.",
            "Corrected Output:",
            "{",
            '  "classification": "negative"',
            "}",
        )
    )


def test_render_multiple_feedback_records_in_given_order() -> None:
    rendered = render_workflow_run_feedback(
        (
            WorkflowRunFeedback(
                id=FIRST_FEEDBACK_ID,
                run_id=RUN_ID,
                disposition=WorkflowRunFeedbackDisposition.BAD,
                reason="Wrong label.",
                created_at=FIRST_CREATED_AT,
            ),
            WorkflowRunFeedback(
                id=SECOND_FEEDBACK_ID,
                run_id=RUN_ID,
                disposition=WorkflowRunFeedbackDisposition.GOOD,
                reason="Reviewed again; the label is defensible.",
                created_at=SECOND_CREATED_AT,
            ),
        )
    )

    lines = rendered.splitlines()

    assert lines[0] == "Feedback: 2"
    assert lines.index("Feedback 1") < lines.index("Feedback 2")
    assert lines.index(f"ID: {FIRST_FEEDBACK_ID}") < lines.index(f"ID: {SECOND_FEEDBACK_ID}")
    assert "Reason: Reviewed again; the label is defensible." in lines

"""Tests for immutable workflow run feedback."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
)

FEEDBACK_ID = UUID("11111111-1111-1111-1111-111111111111")
RUN_ID = UUID("22222222-2222-2222-2222-222222222222")

CREATED_AT = datetime(
    2026,
    8,
    18,
    16,
    0,
    tzinfo=UTC,
)


def test_bad_feedback_records_reason_and_correction() -> None:
    feedback = WorkflowRunFeedback(
        id=FEEDBACK_ID,
        run_id=RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason="The classification was incorrect.",
        corrected_output={
            "classification": "negative",
        },
        created_at=CREATED_AT,
    )

    assert feedback.id == FEEDBACK_ID
    assert feedback.run_id == RUN_ID
    assert feedback.disposition is WorkflowRunFeedbackDisposition.BAD
    assert feedback.reason == ("The classification was incorrect.")
    assert feedback.corrected_output == {
        "classification": "negative",
    }
    assert feedback.created_at == CREATED_AT


def test_good_feedback_does_not_require_reason() -> None:
    feedback = WorkflowRunFeedback(
        id=FEEDBACK_ID,
        run_id=RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
        created_at=CREATED_AT,
    )

    assert feedback.reason is None
    assert feedback.corrected_output is None


@pytest.mark.parametrize(
    "reason",
    (
        None,
        "",
        "   ",
    ),
)
def test_bad_feedback_requires_reason(
    reason: str | None,
) -> None:
    with pytest.raises(
        ValidationError,
        match="Bad workflow run feedback requires a reason",
    ):
        WorkflowRunFeedback(
            id=FEEDBACK_ID,
            run_id=RUN_ID,
            disposition=WorkflowRunFeedbackDisposition.BAD,
            reason=reason,
            created_at=CREATED_AT,
        )


def test_feedback_round_trips_through_json() -> None:
    feedback = WorkflowRunFeedback(
        id=FEEDBACK_ID,
        run_id=RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason="The answer omitted a required field.",
        corrected_output={
            "status": "complete",
        },
        created_at=CREATED_AT,
    )

    restored = WorkflowRunFeedback.model_validate_json(feedback.model_dump_json())

    assert restored == feedback


def test_feedback_is_immutable() -> None:
    feedback = WorkflowRunFeedback(
        id=FEEDBACK_ID,
        run_id=RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
        created_at=CREATED_AT,
    )

    with pytest.raises(ValidationError):
        feedback.reason = "changed"

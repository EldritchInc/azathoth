"""Tests for workflow run feedback repository implementations."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.workflows import (
    InMemoryWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunFeedbackRepository,
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
    WorkflowRunFeedbackRepository,
    require_workflow_run_feedback_repository,
)

FIRST_FEEDBACK_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_FEEDBACK_ID = UUID("22222222-2222-2222-2222-222222222222")
THIRD_FEEDBACK_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_RUN_ID = UUID("44444444-4444-4444-4444-444444444444")
SECOND_RUN_ID = UUID("55555555-5555-5555-5555-555555555555")

CREATED_AT = datetime(
    2026,
    8,
    18,
    16,
    0,
    tzinfo=UTC,
)


def create_feedback(
    *,
    feedback_id: UUID,
    run_id: UUID,
    disposition: WorkflowRunFeedbackDisposition,
    reason: str | None = None,
) -> WorkflowRunFeedback:
    """Create deterministic workflow run feedback."""

    return WorkflowRunFeedback(
        id=feedback_id,
        run_id=run_id,
        disposition=disposition,
        reason=reason,
        created_at=CREATED_AT,
    )


def assert_repository_behavior(
    repository: WorkflowRunFeedbackRepository,
) -> None:
    """Assert common workflow feedback repository behavior."""

    first = create_feedback(
        feedback_id=FIRST_FEEDBACK_ID,
        run_id=FIRST_RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason="The answer was incorrect.",
    )

    second = create_feedback(
        feedback_id=SECOND_FEEDBACK_ID,
        run_id=FIRST_RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
    )

    third = create_feedback(
        feedback_id=THIRD_FEEDBACK_ID,
        run_id=SECOND_RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason="The response omitted a required field.",
    )

    repository.save(first)
    repository.save(second)
    repository.save(third)

    assert repository.get(FIRST_FEEDBACK_ID) == first

    assert repository.feedback() == (
        first,
        second,
        third,
    )

    assert repository.feedback_for_run(FIRST_RUN_ID) == (
        first,
        second,
    )

    assert repository.feedback_for_run(SECOND_RUN_ID) == (third,)


def test_in_memory_feedback_repository_behavior() -> None:
    assert_repository_behavior(InMemoryWorkflowRunFeedbackRepository())


def test_sqlite_feedback_repository_behavior(
    tmp_path: Path,
) -> None:
    assert_repository_behavior(SQLiteWorkflowRunFeedbackRepository(tmp_path / "feedback.db"))


def test_in_memory_feedback_repository_returns_none_for_unknown_id() -> None:
    repository = InMemoryWorkflowRunFeedbackRepository()

    assert repository.get(FIRST_FEEDBACK_ID) is None


def test_sqlite_feedback_repository_returns_none_for_unknown_id(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunFeedbackRepository(tmp_path / "feedback.db")

    assert repository.get(FIRST_FEEDBACK_ID) is None


def test_in_memory_feedback_repository_rejects_duplicate_feedback() -> None:
    repository = InMemoryWorkflowRunFeedbackRepository()

    feedback = create_feedback(
        feedback_id=FIRST_FEEDBACK_ID,
        run_id=FIRST_RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
    )

    repository.save(feedback)

    with pytest.raises(
        ValueError,
        match=(f"Workflow run feedback {FIRST_FEEDBACK_ID} already exists"),
    ):
        repository.save(feedback)


def test_sqlite_feedback_repository_rejects_duplicate_feedback(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRunFeedbackRepository(tmp_path / "feedback.db")

    feedback = create_feedback(
        feedback_id=FIRST_FEEDBACK_ID,
        run_id=FIRST_RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
    )

    repository.save(feedback)

    with pytest.raises(
        ValueError,
        match=(f"Workflow run feedback {FIRST_FEEDBACK_ID} already exists"),
    ):
        repository.save(feedback)


def test_sqlite_feedback_survives_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "feedback.db"

    feedback = WorkflowRunFeedback(
        id=FIRST_FEEDBACK_ID,
        run_id=FIRST_RUN_ID,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason="The classification was incorrect.",
        corrected_output={
            "classification": "negative",
        },
        created_at=CREATED_AT,
    )

    SQLiteWorkflowRunFeedbackRepository(database).save(feedback)

    restored = SQLiteWorkflowRunFeedbackRepository(database).get(FIRST_FEEDBACK_ID)

    assert restored == feedback
    assert restored is not feedback


def test_feedback_repository_satisfies_protocol() -> None:
    repository: WorkflowRunFeedbackRepository = require_workflow_run_feedback_repository(
        InMemoryWorkflowRunFeedbackRepository()
    )

    assert repository.feedback() == ()

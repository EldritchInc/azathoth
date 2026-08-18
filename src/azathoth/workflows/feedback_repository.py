"""Persistence contracts for workflow run feedback."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.feedback import WorkflowRunFeedback


class WorkflowRunFeedbackRepository(Protocol):
    """Persist and retrieve immutable workflow run feedback."""

    def save(
        self,
        feedback: WorkflowRunFeedback,
    ) -> None:
        """Persist one workflow run feedback record."""

        ...

    def get(
        self,
        feedback_id: UUID,
    ) -> WorkflowRunFeedback | None:
        """Return feedback by identifier."""

        ...

    def feedback(
        self,
    ) -> tuple[WorkflowRunFeedback, ...]:
        """Return all feedback records in insertion order."""

        ...

    def feedback_for_run(
        self,
        run_id: UUID,
    ) -> tuple[WorkflowRunFeedback, ...]:
        """Return feedback for one workflow run in insertion order."""

        ...

"""Deterministic in-memory persistence for workflow run feedback."""

from uuid import UUID

from azathoth.workflows.feedback import WorkflowRunFeedback
from azathoth.workflows.feedback_repository import (
    WorkflowRunFeedbackRepository,
)


class InMemoryWorkflowRunFeedbackRepository:
    """Store immutable workflow run feedback in insertion order."""

    def __init__(self) -> None:
        self._feedback: dict[UUID, WorkflowRunFeedback] = {}

    def save(
        self,
        feedback: WorkflowRunFeedback,
    ) -> None:
        """Persist feedback without replacing existing evidence."""

        if feedback.id in self._feedback:
            raise ValueError(f"Workflow run feedback {feedback.id} already exists.")

        self._feedback[feedback.id] = feedback

    def get(
        self,
        feedback_id: UUID,
    ) -> WorkflowRunFeedback | None:
        """Return workflow run feedback by identifier."""

        return self._feedback.get(feedback_id)

    def feedback(
        self,
    ) -> tuple[WorkflowRunFeedback, ...]:
        """Return all feedback records in insertion order."""

        return tuple(self._feedback.values())

    def feedback_for_run(
        self,
        run_id: UUID,
    ) -> tuple[WorkflowRunFeedback, ...]:
        """Return feedback records for one workflow run."""

        return tuple(feedback for feedback in self._feedback.values() if feedback.run_id == run_id)


def require_workflow_run_feedback_repository(
    repository: WorkflowRunFeedbackRepository,
) -> WorkflowRunFeedbackRepository:
    """Return a repository after static protocol validation."""

    return repository

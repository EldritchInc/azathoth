"""Persistence contracts for workflow run evaluations."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.run_evaluation import WorkflowRunEvaluation


class WorkflowRunEvaluationRepository(Protocol):
    """Persist and retrieve evaluator judgments for workflow runs."""

    def save(
        self,
        run_evaluation: WorkflowRunEvaluation,
    ) -> None:
        """Persist one workflow run evaluation."""

        ...

    def get(
        self,
        evaluation_id: UUID,
    ) -> WorkflowRunEvaluation | None:
        """Return one run evaluation by evaluation identifier."""

        ...

    def evaluations(
        self,
    ) -> tuple[WorkflowRunEvaluation, ...]:
        """Return all run evaluations in insertion order."""

        ...

    def evaluations_for_run(
        self,
        run_id: UUID,
    ) -> tuple[WorkflowRunEvaluation, ...]:
        """Return evaluations for one workflow run in insertion order."""

        ...

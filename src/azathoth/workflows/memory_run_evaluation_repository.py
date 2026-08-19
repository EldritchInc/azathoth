"""Deterministic in-memory persistence for workflow run evaluations."""

from uuid import UUID

from azathoth.workflows.run_evaluation import WorkflowRunEvaluation
from azathoth.workflows.run_evaluation_repository import (
    WorkflowRunEvaluationRepository,
)


class InMemoryWorkflowRunEvaluationRepository:
    """Store immutable workflow run evaluations in insertion order."""

    def __init__(self) -> None:
        self._evaluations: dict[UUID, WorkflowRunEvaluation] = {}

    def save(
        self,
        run_evaluation: WorkflowRunEvaluation,
    ) -> None:
        """Persist one evaluation without replacing existing evidence."""

        if run_evaluation.id in self._evaluations:
            raise ValueError(f"Workflow run evaluation {run_evaluation.id} already exists.")

        self._evaluations[run_evaluation.id] = run_evaluation

    def get(
        self,
        evaluation_id: UUID,
    ) -> WorkflowRunEvaluation | None:
        """Return one run evaluation by evaluation identifier."""

        return self._evaluations.get(evaluation_id)

    def evaluations(
        self,
    ) -> tuple[WorkflowRunEvaluation, ...]:
        """Return all run evaluations in insertion order."""

        return tuple(self._evaluations.values())

    def evaluations_for_run(
        self,
        run_id: UUID,
    ) -> tuple[WorkflowRunEvaluation, ...]:
        """Return evaluations for one workflow run in insertion order."""

        return tuple(
            run_evaluation
            for run_evaluation in self._evaluations.values()
            if run_evaluation.run_id == run_id
        )


def require_workflow_run_evaluation_repository(
    repository: WorkflowRunEvaluationRepository,
) -> WorkflowRunEvaluationRepository:
    """Return a repository after static protocol validation."""

    return repository

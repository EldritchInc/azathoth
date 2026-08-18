"""Deterministic in-memory persistence for workflow run evidence."""

from uuid import UUID

from azathoth.workflows.execution import WorkflowRun
from azathoth.workflows.run_repository import WorkflowRunRepository


class InMemoryWorkflowRunRepository:
    """Store immutable workflow runs in insertion order."""

    def __init__(self) -> None:
        self._runs: dict[UUID, WorkflowRun] = {}

    def save(
        self,
        run: WorkflowRun,
    ) -> None:
        """Persist one workflow run without replacing existing evidence."""

        if run.id in self._runs:
            raise ValueError(f"Workflow run {run.id} already exists.")

        self._runs[run.id] = run

    def get(
        self,
        run_id: UUID,
    ) -> WorkflowRun | None:
        """Return a workflow run by identifier."""

        return self._runs.get(run_id)

    def runs(
        self,
    ) -> tuple[WorkflowRun, ...]:
        """Return all workflow runs in insertion order."""

        return tuple(self._runs.values())

    def runs_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowRun, ...]:
        """Return workflow runs matching one workflow identifier."""

        return tuple(run for run in self._runs.values() if run.workflow.id == workflow_id)


def require_workflow_run_repository(
    repository: WorkflowRunRepository,
) -> WorkflowRunRepository:
    """Return a repository after static protocol validation."""

    return repository

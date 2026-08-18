"""Persistence contracts for durable workflow run evidence."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.execution import WorkflowRun


class WorkflowRunRepository(Protocol):
    """Persist and retrieve completed workflow run evidence."""

    def save(
        self,
        run: WorkflowRun,
    ) -> None:
        """Persist one completed workflow run."""

        ...

    def get(
        self,
        run_id: UUID,
    ) -> WorkflowRun | None:
        """Return a workflow run by identifier."""

        ...

    def runs(
        self,
    ) -> tuple[WorkflowRun, ...]:
        """Return all persisted workflow runs in insertion order."""

        ...

    def runs_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowRun, ...]:
        """Return persisted runs for one workflow in insertion order."""

        ...

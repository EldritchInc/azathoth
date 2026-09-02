"""Persistence contracts for workflow production state."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.production import WorkflowProductionState


class WorkflowProductionStateRepository(Protocol):
    """Persist the currently active production state for workflows."""

    def set(
        self,
        state: WorkflowProductionState,
    ) -> None:
        """Set the active production state for one workflow."""

        ...

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowProductionState | None:
        """Return the active production state for one workflow."""

        ...

    def states(
        self,
    ) -> tuple[WorkflowProductionState, ...]:
        """Return all active production states in deterministic order."""

        ...

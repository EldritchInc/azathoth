"""Deterministic in-memory persistence for workflow production state."""

from uuid import UUID

from azathoth.workflows.production import WorkflowProductionState
from azathoth.workflows.production_repository import (
    WorkflowProductionStateRepository,
)


class InMemoryWorkflowProductionStateRepository:
    """Store active workflow production state by workflow identity."""

    def __init__(
        self,
    ) -> None:
        self._states: dict[
            UUID,
            WorkflowProductionState,
        ] = {}

    def set(
        self,
        state: WorkflowProductionState,
    ) -> None:
        """Set the active production state for one workflow."""

        workflow_id = state.specification.metadata.id

        self._states[workflow_id] = state

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowProductionState | None:
        """Return the active production state for one workflow."""

        return self._states.get(workflow_id)

    def states(
        self,
    ) -> tuple[WorkflowProductionState, ...]:
        """Return all active production states in deterministic order."""

        return tuple(self._states.values())


def require_workflow_production_state_repository(
    repository: WorkflowProductionStateRepository,
) -> WorkflowProductionStateRepository:
    """Return a repository after static protocol validation."""

    return repository

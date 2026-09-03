"""Deterministic in-memory persistence for workflow production revisions."""

from uuid import UUID

from azathoth.workflows.production import WorkflowProductionRevision
from azathoth.workflows.production_revision_repository import (
    WorkflowProductionRevisionRepository,
)


class InMemoryWorkflowProductionRevisionRepository:
    """Store immutable production revisions in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._revisions: dict[
            UUID,
            WorkflowProductionRevision,
        ] = {}

    def save(
        self,
        revision: WorkflowProductionRevision,
    ) -> None:
        """Persist one production revision without replacing history."""

        if revision.id in self._revisions:
            raise ValueError(f"Workflow production revision {revision.id} already exists.")

        self._revisions[revision.id] = revision

    def get(
        self,
        revision_id: UUID,
    ) -> WorkflowProductionRevision | None:
        """Return one production revision by identifier."""

        return self._revisions.get(revision_id)

    def revisions(
        self,
    ) -> tuple[WorkflowProductionRevision, ...]:
        """Return all production revisions in insertion order."""

        return tuple(self._revisions.values())

    def revisions_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowProductionRevision, ...]:
        """Return production revisions for one workflow in insertion order."""

        return tuple(
            revision for revision in self._revisions.values() if revision.workflow_id == workflow_id
        )


def require_workflow_production_revision_repository(
    repository: WorkflowProductionRevisionRepository,
) -> WorkflowProductionRevisionRepository:
    """Return a repository after static protocol validation."""

    return repository

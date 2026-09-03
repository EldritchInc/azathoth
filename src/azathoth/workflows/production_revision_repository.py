"""Persistence contracts for immutable workflow production revisions."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.production import WorkflowProductionRevision


class WorkflowProductionRevisionRepository(Protocol):
    """Persist immutable historical workflow production revisions."""

    def save(
        self,
        revision: WorkflowProductionRevision,
    ) -> None:
        """Persist one production revision without replacing history."""

        ...

    def get(
        self,
        revision_id: UUID,
    ) -> WorkflowProductionRevision | None:
        """Return one production revision by identifier."""

        ...

    def revisions(
        self,
    ) -> tuple[WorkflowProductionRevision, ...]:
        """Return all production revisions in insertion order."""

        ...

    def revisions_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowProductionRevision, ...]:
        """Return production revisions for one workflow in insertion order."""

        ...

"""Deterministic in-memory persistence for workflow specifications."""

from uuid import UUID

from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.repository import WorkflowRepository


class InMemoryWorkflowRepository:
    """Store workflow specifications in insertion order."""

    def __init__(self) -> None:
        self._specifications: dict[UUID, WorkflowSpecification] = {}

    def save(
        self,
        specification: WorkflowSpecification,
    ) -> None:
        """Persist one workflow specification without replacing existing data."""

        workflow_id = specification.metadata.id

        if workflow_id in self._specifications:
            raise ValueError(f"Workflow specification {workflow_id} already exists.")

        self._specifications[workflow_id] = specification

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecification | None:
        """Return a workflow specification by identifier."""

        return self._specifications.get(workflow_id)

    def specifications(
        self,
    ) -> tuple[WorkflowSpecification, ...]:
        """Return all persisted workflow specifications in insertion order."""

        return tuple(self._specifications.values())


def require_workflow_repository(
    repository: WorkflowRepository,
) -> WorkflowRepository:
    """Return a repository after static protocol validation."""

    return repository

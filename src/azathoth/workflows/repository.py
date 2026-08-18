"""Persistence contracts for durable workflow specifications."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.models import WorkflowSpecification


class WorkflowRepository(Protocol):
    """Persist and retrieve durable workflow specifications."""

    def save(
        self,
        specification: WorkflowSpecification,
    ) -> None:
        """Persist one workflow specification."""

        ...

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecification | None:
        """Return a workflow specification by identifier."""

        ...

    def specifications(
        self,
    ) -> tuple[WorkflowSpecification, ...]:
        """Return all persisted workflow specifications in insertion order."""

        ...

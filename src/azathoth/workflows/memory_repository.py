"""Deterministic in-memory persistence for workflow specifications."""

from uuid import UUID

from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.repository import WorkflowRepository
from azathoth.workflows.revision import WorkflowSpecificationRevision


class InMemoryWorkflowRepository:
    """Store revisioned workflow specifications in import order."""

    def __init__(self) -> None:
        self._revisions: dict[
            UUID,
            list[WorkflowSpecificationRevision],
        ] = {}

    def save(
        self,
        specification: WorkflowSpecification,
    ) -> WorkflowSpecificationRevision:
        """Append one specification as its workflow's next revision."""

        history = self._revisions.setdefault(
            specification.metadata.id,
            [],
        )

        revision = WorkflowSpecificationRevision.create(
            specification,
            number=len(history) + 1,
        )

        history.append(revision)

        return revision

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecification | None:
        """Return a workflow's latest specification."""

        revision = self.latest_revision(workflow_id)

        return revision.specification if revision is not None else None

    def specifications(
        self,
    ) -> tuple[WorkflowSpecification, ...]:
        """Return every workflow's latest specification in first-import order."""

        return tuple(history[-1].specification for history in self._revisions.values())

    def latest_revision(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecificationRevision | None:
        """Return a workflow's latest revision."""

        history = self._revisions.get(workflow_id)

        return history[-1] if history else None

    def revision(
        self,
        workflow_id: UUID,
        number: int,
    ) -> WorkflowSpecificationRevision | None:
        """Return one numbered revision of a workflow."""

        return next(
            (
                revision
                for revision in self._revisions.get(workflow_id, ())
                if revision.number == number
            ),
            None,
        )

    def revisions(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowSpecificationRevision, ...]:
        """Return every revision of a workflow, oldest first."""

        return tuple(self._revisions.get(workflow_id, ()))


def require_workflow_repository(
    repository: WorkflowRepository,
) -> WorkflowRepository:
    """Return a repository after static protocol validation."""

    return repository

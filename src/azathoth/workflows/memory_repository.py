"""Deterministic in-memory persistence for workflow specifications."""

from uuid import UUID

from azathoth.revisions import (
    Author,
    Lineage,
    LineageRecord,
    RevisionKind,
    SavedRevision,
    base_record,
    child_record,
    content_digest,
)
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

        self._lineage: dict[
            UUID,
            list[LineageRecord],
        ] = {}

    def save(
        self,
        specification: WorkflowSpecification,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> WorkflowSpecificationRevision:
        """Append one specification as its workflow's next revision, and return it."""

        return self.save_revision(
            specification,
            author=author,
            based_on=based_on,
        ).revision

    def save_revision(
        self,
        specification: WorkflowSpecification,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> SavedRevision[WorkflowSpecificationRevision]:
        """Append one specification on the revision it builds on, unless it is identical to it.

        Raises:
            BaseRevisionError: No revision of the workflow has the digest
                `based_on`.
        """

        workflow_id = specification.metadata.id
        lineage = Lineage(kind=RevisionKind.WORKFLOW, id=workflow_id)

        records = self._lineage.setdefault(workflow_id, [])
        history = self._revisions.setdefault(workflow_id, [])

        parent = base_record(records, lineage, based_on)

        if parent is not None:
            built_on = history[parent.number - 1]

            if built_on.content_digest == content_digest(specification):
                return SavedRevision(revision=built_on, lineage=parent, created=False)

        revision = WorkflowSpecificationRevision.create(
            specification,
            number=len(history) + 1,
        )

        record = child_record(
            lineage,
            number=revision.number,
            content_digest=revision.content_digest,
            parent=parent,
            author=author,
        )

        history.append(revision)
        records.append(record)

        return SavedRevision(revision=revision, lineage=record, created=True)

    def lineage(
        self,
        workflow_id: UUID,
    ) -> tuple[LineageRecord, ...]:
        """Return the lineage record of every revision of a workflow, oldest first."""

        return tuple(self._lineage.get(workflow_id, ()))

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

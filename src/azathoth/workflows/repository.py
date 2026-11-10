"""Persistence contracts for durable workflow specifications."""

from typing import Protocol
from uuid import UUID

from azathoth.revisions import Author, LineageRecord, SavedRevision
from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.revision import WorkflowSpecificationRevision


class WorkflowRepository(Protocol):
    """Persist and retrieve revisioned workflow specifications.

    The workflow ID is a lineage. Saving never replaces anything: each save
    appends the next revision under the specification's workflow ID, and the
    latest revision is the workflow's current specification. A save
    identical to the revision it builds on appends nothing.
    """

    def save(
        self,
        specification: WorkflowSpecification,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> WorkflowSpecificationRevision:
        """Append one specification as its workflow's next revision, and return it."""

        ...

    def save_revision(
        self,
        specification: WorkflowSpecification,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> SavedRevision[WorkflowSpecificationRevision]:
        """Append one specification on the revision it builds on, unless it is identical to it.

        It builds on the revision whose revision digest is `based_on`, or on
        the latest without one (ADR 0122).

        Raises:
            BaseRevisionError: No revision of the workflow has that digest.
        """

        ...

    def lineage(
        self,
        workflow_id: UUID,
    ) -> tuple[LineageRecord, ...]:
        """Return the lineage record of every revision of a workflow, oldest first."""

        ...

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecification | None:
        """Return a workflow's latest specification."""

        ...

    def specifications(
        self,
    ) -> tuple[WorkflowSpecification, ...]:
        """Return every workflow's latest specification in first-import order."""

        ...

    def latest_revision(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecificationRevision | None:
        """Return a workflow's latest revision."""

        ...

    def revision(
        self,
        workflow_id: UUID,
        number: int,
    ) -> WorkflowSpecificationRevision | None:
        """Return one numbered revision of a workflow."""

        ...

    def revisions(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowSpecificationRevision, ...]:
        """Return every revision of a workflow, oldest first."""

        ...

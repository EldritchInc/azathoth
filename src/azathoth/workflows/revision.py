"""Immutable revisions of durable workflow specifications."""

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.revisions import (
    CONTENT_DIGEST_PATTERN,
    content_digest,
)
from azathoth.workflows.models import WorkflowSpecification


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class WorkflowSpecificationRevision(BaseModel):
    """Record one import of a workflow specification under its workflow ID.

    The workflow ID is the lineage; every import appends the next revision
    number and nothing is ever replaced. Re-importing an earlier document,
    for example to revert a change, appends a new revision whose digest
    matches the earlier one.
    """

    model_config = ConfigDict(frozen=True)

    workflow_id: UUID

    number: int = Field(
        ge=1,
    )

    specification: WorkflowSpecification

    content_digest: str = Field(
        pattern=CONTENT_DIGEST_PATTERN,
    )

    imported_at: datetime = Field(
        default_factory=utc_now,
    )

    @model_validator(mode="after")
    def validate_specification_identity(
        self,
    ) -> "WorkflowSpecificationRevision":
        """Require the specification to belong to the revision's workflow."""

        if self.specification.metadata.id != self.workflow_id:
            raise ValueError("Workflow revision specification must belong to its workflow.")

        return self

    @classmethod
    def create(
        cls,
        specification: WorkflowSpecification,
        *,
        number: int,
        imported_at: datetime | None = None,
    ) -> "WorkflowSpecificationRevision":
        """Return the revision recording one import of a specification.

        The digest is computed from the specification as imported.
        """

        return cls(
            workflow_id=specification.metadata.id,
            number=number,
            specification=specification,
            content_digest=content_digest(specification),
            imported_at=imported_at if imported_at is not None else utc_now(),
        )


def earliest_identical_revision(
    history: Iterable[WorkflowSpecificationRevision],
    revision: WorkflowSpecificationRevision,
) -> WorkflowSpecificationRevision | None:
    """Return the earliest other revision with the same content, if any.

    Only revisions of the same workflow with a lower number are considered,
    so the result names the revision a re-import reverted to.
    """

    matches = sorted(
        (
            candidate
            for candidate in history
            if candidate.workflow_id == revision.workflow_id
            and candidate.number < revision.number
            and candidate.content_digest == revision.content_digest
        ),
        key=lambda candidate: candidate.number,
    )

    return matches[0] if matches else None

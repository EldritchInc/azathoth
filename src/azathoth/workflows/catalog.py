"""Immutable catalog of durable workflow specifications."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.workflows.models import WorkflowSpecification


class WorkflowCatalog(BaseModel):
    """A reproducible inventory of durable workflow specifications.

    Revisions map workflow IDs to the revision number of each catalogued
    specification. A catalog built from a revisioned repository holds each
    workflow's latest revision; a workflow without an entry has no known
    revision.
    """

    model_config = ConfigDict(frozen=True)

    specifications: tuple[WorkflowSpecification, ...] = ()

    revisions: dict[UUID, int] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> "WorkflowCatalog":
        """Reject duplicate workflow identifiers."""

        identifiers = tuple(specification.metadata.id for specification in self.specifications)

        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Workflow catalog cannot contain duplicate workflow identifiers.")

        return self

    @model_validator(mode="after")
    def validate_revisions(self) -> "WorkflowCatalog":
        """Require revisions to name catalogued workflows and positive numbers."""

        if not set(self.revisions).issubset(self.identifiers):
            raise ValueError("Workflow catalog revisions must reference catalogued workflows.")

        if any(number < 1 for number in self.revisions.values()):
            raise ValueError("Workflow catalog revision numbers must be at least 1.")

        return self

    @property
    def identifiers(self) -> tuple[UUID, ...]:
        """Return workflow identifiers in catalog order."""

        return tuple(specification.metadata.id for specification in self.specifications)

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecification | None:
        """Return a workflow specification by exact identifier."""

        return next(
            (
                specification
                for specification in self.specifications
                if specification.metadata.id == workflow_id
            ),
            None,
        )

    def revision_number(
        self,
        workflow_id: UUID,
    ) -> int | None:
        """Return the revision number of one catalogued workflow, if known."""

        return self.revisions.get(workflow_id)

    def specifications_named(
        self,
        name: str,
    ) -> tuple[WorkflowSpecification, ...]:
        """Return workflow specifications with an exact name."""

        return tuple(
            specification
            for specification in self.specifications
            if specification.metadata.name == name
        )

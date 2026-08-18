"""Immutable catalog of durable workflow specifications."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from azathoth.workflows.models import WorkflowSpecification


class WorkflowCatalog(BaseModel):
    """A reproducible inventory of durable workflow specifications."""

    model_config = ConfigDict(frozen=True)

    specifications: tuple[WorkflowSpecification, ...] = ()

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> "WorkflowCatalog":
        """Reject duplicate workflow identifiers."""

        identifiers = tuple(specification.metadata.id for specification in self.specifications)

        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Workflow catalog cannot contain duplicate workflow identifiers.")

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

"""Domain models describing model-independent workflows."""

from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from azathoth.workflows.steps import WorkflowStepSpecification


class WorkflowMetadata(BaseModel):
    """Stable identifying information for a workflow specification."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)


class WorkflowSpecification(BaseModel):
    """Describe an ordered workflow without runtime dependencies."""

    model_config = ConfigDict(frozen=True)

    metadata: WorkflowMetadata

    steps: tuple[WorkflowStepSpecification, ...] = Field(
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> Self:
        """Ensure every workflow step has a unique identifier."""

        step_ids = tuple(step.id for step in self.steps)

        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Workflow step identifiers must be unique.")

        return self

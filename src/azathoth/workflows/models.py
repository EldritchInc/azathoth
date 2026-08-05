"""Domain models describing model-independent workflows."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

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
    steps: tuple[WorkflowStepSpecification, ...]

"""Workflow step specifications."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from azathoth.prompting import PromptStrategySpec
from azathoth.workflows.value import WorkflowValueBinding


class WorkflowStepSpecification(BaseModel):
    """Describe one independently configured step of a workflow."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    specification: PromptStrategySpec
    depends_on: tuple[UUID, ...] = ()
    outputs: tuple[WorkflowValueBinding, ...] = ()

"""Workflow step specifications."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from azathoth.prompting import PromptStrategySpec
from azathoth.workflows.condition import WorkflowCondition
from azathoth.workflows.value import WorkflowInputBinding, WorkflowValueBinding


class WorkflowStepSpecification(BaseModel):
    """Describe one independently configured step of a workflow."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    specification: PromptStrategySpec
    depends_on: tuple[UUID, ...] = ()
    inputs: tuple[WorkflowInputBinding, ...] = ()
    outputs: tuple[WorkflowValueBinding, ...] = ()
    conditions: tuple[WorkflowCondition, ...] = ()

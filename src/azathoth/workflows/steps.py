"""Workflow step specifications."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from azathoth.prompting import PromptStrategySpec


class WorkflowStepSpecification(BaseModel):
    """Describe one step of a workflow."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    specification: PromptStrategySpec

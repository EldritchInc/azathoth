"""Workflow step specifications."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from azathoth.prompting import PromptStrategySpec
from azathoth.tools import ToolRequirement
from azathoth.workflows.condition import WorkflowCondition
from azathoth.workflows.failure import WorkflowFailurePolicy
from azathoth.workflows.retry import WorkflowRetryPolicy
from azathoth.workflows.value import (
    WorkflowInputBinding,
    WorkflowValueBinding,
)


class ToolStepSpecification(BaseModel):
    """Describe a workflow step backed by a durable tool capability."""

    model_config = ConfigDict(frozen=True)

    requirement: ToolRequirement


class WorkflowStepSpecification(BaseModel):
    """Describe one independently configured step of a workflow."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    specification: PromptStrategySpec | ToolStepSpecification
    depends_on: tuple[UUID, ...] = ()
    inputs: tuple[WorkflowInputBinding, ...] = ()
    outputs: tuple[WorkflowValueBinding, ...] = ()
    conditions: tuple[WorkflowCondition, ...] = ()
    retry_policy: WorkflowRetryPolicy = Field(
        default_factory=WorkflowRetryPolicy,
    )
    failure_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.FAIL_WORKFLOW

"""Workflow step specifications."""

from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from azathoth.prompting import (
    ContextPromptStrategySpec,
    PromptStrategySpec,
)
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
    """Describe one independently configured step of a workflow.

    The optional message is what the step tells whoever is watching the
    workflow when it starts, for example "Counting words". A step without a
    message is silent. A step with a message may also emit its declared
    values once it succeeds. Both are presentation only: they never change
    how the step executes, is evaluated, or is optimized.

    A step that leaves them unset serializes without them, so its documents
    and content digests are unchanged.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    specification: PromptStrategySpec | ContextPromptStrategySpec | ToolStepSpecification

    depends_on: tuple[UUID, ...] = ()
    inputs: tuple[WorkflowInputBinding, ...] = ()
    outputs: tuple[WorkflowValueBinding, ...] = ()
    conditions: tuple[WorkflowCondition, ...] = ()

    retry_policy: WorkflowRetryPolicy = Field(
        default_factory=WorkflowRetryPolicy,
    )

    failure_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.FAIL_WORKFLOW

    message: str | None = Field(
        default=None,
        min_length=1,
    )

    emit_values: bool = False

    @model_validator(mode="after")
    def validate_emitted_values(self) -> Self:
        """Ensure a step emits values only alongside a message and declared outputs.

        Raises:
            ValueError: The step emits values without a message, or without
                declared outputs.
        """

        if not self.emit_values:
            return self

        if self.message is None:
            raise ValueError(f"Workflow step {self.id} emits values but declares no message.")

        if not self.outputs:
            raise ValueError(f"Workflow step {self.id} emits values but declares no outputs.")

        return self

    @model_serializer(mode="wrap")
    def serialize_without_unset_presentation_fields(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the step, omitting an unset message and disabled value emission."""

        serialized: dict[str, Any] = handler(self)

        if serialized.get("message") is None:
            serialized.pop("message", None)

        if not serialized.get("emit_values"):
            serialized.pop("emit_values", None)

        return serialized

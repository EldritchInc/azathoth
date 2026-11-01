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
    PromptInputBinding,
    PromptSpecification,
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

    The optional confidence names one of the step's declared outputs as the
    step's confidence in what it produced (ADR 0098). A step without one
    serializes without it.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    specification: PromptSpecification | ToolStepSpecification

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

    confidence: str | None = Field(
        default=None,
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_confidence_output(self) -> Self:
        """Ensure a declared confidence names one of the step's declared outputs.

        Raises:
            ValueError: The confidence names an output the step does not
                declare.
        """

        if self.confidence is None:
            return self

        if self.confidence not in {binding.name for binding in self.outputs}:
            raise ValueError(
                f"Workflow step {self.id} declares confidence {self.confidence!r}, "
                "which is not one of its declared outputs."
            )

        return self

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

    @model_validator(mode="after")
    def validate_prompt_input_bindings(self) -> Self:
        """Ensure every prompt variable bound to a step input names a declared input.

        Raises:
            ValueError: A prompt variable binds an input the step does not
                declare.
        """

        if not isinstance(self.specification, ContextPromptStrategySpec):
            return self

        declared = {binding.name for binding in self.inputs}

        for binding in self.specification.template.bindings:
            if isinstance(binding, PromptInputBinding) and binding.input_name not in declared:
                raise ValueError(
                    f"Workflow step {self.id} prompt variable {binding.variable_name!r} "
                    f"binds input {binding.input_name!r}, which the step does not declare."
                )

        return self

    @model_serializer(mode="wrap")
    def serialize_without_unset_presentation_fields(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the step, omitting unset presentation fields and confidence."""

        serialized: dict[str, Any] = handler(self)

        if serialized.get("message") is None:
            serialized.pop("message", None)

        if not serialized.get("emit_values"):
            serialized.pop("emit_values", None)

        if serialized.get("confidence") is None:
            serialized.pop("confidence", None)

        return serialized

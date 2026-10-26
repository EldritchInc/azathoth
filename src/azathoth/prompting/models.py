"""Domain models for rendering prompts from structured context."""

import json

from pydantic import BaseModel, ConfigDict, Field

from azathoth.context import Context
from azathoth.prompting.exceptions import (
    ModelBindingMismatchError,
    PromptBindingEventNotFoundError,
    PromptBindingFieldNotFoundError,
    PromptBindingInputNotFoundError,
)
from azathoth.providers import ModelResponse, Prompt


class ModelBinding(BaseModel):
    """Identify the catalog model bound to an executable prompt strategy."""

    model_config = ConfigDict(frozen=True)

    identifier: str = Field(min_length=1)

    def validate_response(
        self,
        response: ModelResponse,
    ) -> None:
        """Ensure a model response came from the configured model."""

        reported_identifier = f"{response.provider}/{response.model}"

        if reported_identifier != self.identifier:
            raise ModelBindingMismatchError(
                "Model response identifier "
                f"{reported_identifier!r} does not match configured "
                f"binding {self.identifier!r}."
            )


WORKFLOW_INPUT_BOUND_EVENT_TYPE = "workflow.input.bound"
"""The event a workflow runner records for each value bound to a step input."""


class PromptBinding(BaseModel):
    """Bind one prompt variable to a field in the latest matching event."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    variable_name: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    field_name: str = Field(min_length=1)


class PromptInputBinding(BaseModel):
    """Bind one prompt variable to a workflow step input by the input's name.

    The variable takes the value of the latest bound input with that name.
    The workflow runner binds a step's own inputs last, so an earlier step's
    input of the same name never wins.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    variable_name: str = Field(min_length=1)
    input_name: str = Field(min_length=1)


def render_prompt_value(
    value: object,
) -> str:
    """Return the text one bound value contributes to a prompt.

    Strings are inserted unchanged. Every other value is rendered as compact
    JSON with non-ASCII characters kept, so structured values reach the model
    as JSON rather than as Python representations.
    """

    if isinstance(value, str):
        return value

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )


class PromptTemplate(BaseModel):
    """A prompt template rendered from structured context events.

    Template text is formatted with `str.format_map`, so literal braces, such
    as an example JSON reply, must be doubled: `{{"verdict": "pass"}}`.
    """

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    bindings: tuple[PromptBinding | PromptInputBinding, ...] = ()

    def render(self, context: Context) -> Prompt:
        """Render this template using values resolved from context.

        Raises:
            PromptBindingEventNotFoundError: An event-field binding has no
                matching context event.
            PromptBindingFieldNotFoundError: The matching event lacks the
                bound field.
            PromptBindingInputNotFoundError: An input binding has no bound
                workflow input with its name.
        """

        values: dict[str, str] = {}

        for binding in self.bindings:
            if isinstance(binding, PromptInputBinding):
                values[binding.variable_name] = render_prompt_value(
                    _bound_input_value(context, binding),
                )

                continue

            event = context.latest(binding.event_type)

            if event is None:
                raise PromptBindingEventNotFoundError(
                    f"No context event found with type "
                    f"{binding.event_type!r} for prompt variable "
                    f"{binding.variable_name!r}."
                )

            if binding.field_name not in event.payload:
                raise PromptBindingFieldNotFoundError(
                    f"Context event {binding.event_type!r} does not "
                    f"contain field {binding.field_name!r} required by "
                    f"prompt variable {binding.variable_name!r}."
                )

            values[binding.variable_name] = render_prompt_value(
                event.payload[binding.field_name],
            )

        return Prompt(
            text=self.text.format_map(values),
        )


def _bound_input_value(
    context: Context,
    binding: PromptInputBinding,
) -> object:
    """Return the value of the latest bound workflow input with the binding's name.

    Raises:
        PromptBindingInputNotFoundError: No input with that name was bound.
    """

    for event in reversed(context.by_type(WORKFLOW_INPUT_BOUND_EVENT_TYPE)):
        if event.payload.get("name") == binding.input_name:
            return event.payload.get("value")

    raise PromptBindingInputNotFoundError(
        f"No bound workflow input named {binding.input_name!r} "
        f"for prompt variable {binding.variable_name!r}."
    )

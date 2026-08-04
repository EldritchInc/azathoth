"""Domain models for rendering prompts from structured context."""

from pydantic import BaseModel, ConfigDict, Field

from azathoth.context import Context
from azathoth.prompting.exceptions import (
    PromptBindingEventNotFoundError,
    PromptBindingFieldNotFoundError,
    ModelBindingMismatchError,
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

        reported_identifier = (
            f"{response.provider}/{response.model}"
        )

        if reported_identifier != self.identifier:
            raise ModelBindingMismatchError(
                "Model response identifier "
                f"{reported_identifier!r} does not match configured "
                f"binding {self.identifier!r}."
            )


class PromptBinding(BaseModel):
    """Bind one prompt variable to a field in the latest matching event."""

    model_config = ConfigDict(frozen=True)

    variable_name: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    field_name: str = Field(min_length=1)


class PromptTemplate(BaseModel):
    """A prompt template rendered from structured context events."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    bindings: tuple[PromptBinding, ...] = ()

    def render(self, context: Context) -> Prompt:
        """Render this template using values resolved from context."""

        values: dict[str, object] = {}

        for binding in self.bindings:
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

            values[binding.variable_name] = event.payload[
                binding.field_name
            ]

        return Prompt(
            text=self.text.format_map(values),
        )



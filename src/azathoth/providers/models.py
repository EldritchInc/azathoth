"""Language model domain, request and response models."""

from enum import StrEnum
from typing import Any, Self, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from azathoth.inputs import ContentRef


class ModelModality(StrEnum):
    """An input or output modality supported by a model."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    EMBEDDINGS = "embeddings"


class ModelCapability(StrEnum):
    """A discrete capability advertised by a language model."""

    STRUCTURED_OUTPUT = "structured_output"
    TOOL_USE = "tool_use"
    VISION = "vision"
    STREAMING = "streaming"


class ModelPricing(BaseModel):
    """Configured model pricing per million tokens."""

    model_config = ConfigDict(frozen=True)

    input_usd_per_million_tokens: float = Field(ge=0.0)
    output_usd_per_million_tokens: float = Field(ge=0.0)


class ModelMetadata(BaseModel):
    """Configured identity and capabilities for an available model."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    display_name: str = Field(min_length=1)

    input_modalities: frozenset[ModelModality] = frozenset({ModelModality.TEXT})
    output_modalities: frozenset[ModelModality] = frozenset({ModelModality.TEXT})
    capabilities: frozenset[ModelCapability] = frozenset()
    context_window_tokens: int | None = Field(
        default=None,
        gt=0,
    )
    maximum_output_tokens: int | None = Field(default=None, gt=0)
    pricing: ModelPricing | None = None

    @property
    def identifier(self) -> str:
        """Return the provider-qualified model identifier."""

        return f"{self.provider}/{self.model}"


class TextPart(BaseModel):
    """Text, as one part of a prompt that also shows content (ADR 0115)."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    text: str = Field(min_length=1)


class ContentPart(BaseModel):
    """Content a prompt shows a model, by its handle: `{"content": {...}}` (ADR 0115).

    A part names content and never holds its bytes, so a prompt can be kept
    and recorded wherever it goes; the bytes are read from the content store
    only as the prompt is sent.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    content: ContentRef


PromptPart: TypeAlias = TextPart | ContentPart
"""One part of a prompt that shows content: text, or content by its handle."""


class Prompt(BaseModel):
    """A rendered prompt sent to a language model.

    A prompt is its `text`, or, when it shows a model content, its `parts`:
    text and content in order, as many of each as it needs (ADR 0115). Never
    both, so a prompt says what it holds once. A prompt of text serializes
    without parts, and a prompt of parts without text, so a text prompt's
    documents and digests are what they were.
    """

    model_config = ConfigDict(frozen=True)

    text: str = ""
    parts: tuple[PromptPart, ...] = ()

    @model_validator(mode="after")
    def require_text_or_content(
        self,
    ) -> Self:
        """Require text alone, or parts that show content, with no text beside them.

        Raises:
            ValueError: The prompt has neither, both, or parts that show no
                content.
        """

        if not self.parts:
            if "text" not in self.model_fields_set:
                raise ValueError("A prompt holds its text, or parts that show content.")

            return self

        if "text" in self.model_fields_set:
            raise ValueError("A prompt holds its text or its parts, not both.")

        if not self.contents():
            raise ValueError(
                "A prompt's parts show content; a prompt of text alone holds it as its text."
            )

        return self

    @model_serializer(mode="wrap")
    def serialize_text_or_parts(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the prompt's text, or its parts, and never the other."""

        serialized: dict[str, Any] = handler(self)

        if self.parts:
            serialized.pop("text", None)
        else:
            serialized.pop("parts", None)

        return serialized

    def contents(
        self,
    ) -> tuple[ContentRef, ...]:
        """Return the content the prompt shows, in order, once for each time it shows it."""

        return tuple(part.content for part in self.parts if isinstance(part, ContentPart))

    def text_parts(
        self,
    ) -> tuple[str, ...]:
        """Return the prompt's text: its text alone, or each of its text parts in order."""

        if not self.parts:
            return (self.text,)

        return tuple(part.text for part in self.parts if isinstance(part, TextPart))


class ModelRequest(BaseModel):
    """A provider-neutral request for a language model completion."""

    model_config = ConfigDict(frozen=True)

    prompt: Prompt
    temperature: float | None = Field(default=None, ge=0.0)
    max_output_tokens: int | None = Field(default=None, gt=0)


class ModelResponse(BaseModel):
    """The response returned by a language model.

    `estimated_cost_usd` is None when the cost is unknown, such as for a
    Bedrock model its operator has not priced (ADR 0103). Unknown is never
    free.
    """

    model_config = ConfigDict(frozen=True)

    text: str

    provider: str
    model: str
    resolved_model: str | None = None

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    latency_ms: int

    estimated_cost_usd: float | None

"""Language model domain, request and response models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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


class Prompt(BaseModel):
    """A rendered prompt sent to a language model."""

    model_config = ConfigDict(frozen=True)

    text: str


class ModelRequest(BaseModel):
    """A provider-neutral request for a language model completion."""

    model_config = ConfigDict(frozen=True)

    prompt: Prompt
    temperature: float | None = Field(default=None, ge=0.0)
    max_output_tokens: int | None = Field(default=None, gt=0)


class ModelResponse(BaseModel):
    """The response returned by a language model."""

    model_config = ConfigDict(frozen=True)

    text: str

    provider: str
    model: str
    resolved_model: str | None = None

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    latency_ms: int

    estimated_cost_usd: float

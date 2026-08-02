"""Provider-neutral requirements declared by model-backed workloads."""

from pydantic import BaseModel, ConfigDict, Field

from azathoth.providers.models import (
    ModelCapability,
    ModelModality,
)


class ModelRequirements(BaseModel):
    """Capabilities and limits required from a language model."""

    model_config = ConfigDict(frozen=True)

    required_capabilities: frozenset[ModelCapability] = frozenset()
    required_input_modalities: frozenset[ModelModality] = frozenset({ModelModality.TEXT})
    required_output_modalities: frozenset[ModelModality] = frozenset({ModelModality.TEXT})

    minimum_context_window_tokens: int | None = Field(
        default=None,
        gt=0,
    )
    minimum_output_tokens: int | None = Field(
        default=None,
        gt=0,
    )

    maximum_input_usd_per_million_tokens: float | None = Field(
        default=None,
        ge=0.0,
    )
    maximum_output_usd_per_million_tokens: float | None = Field(
        default=None,
        ge=0.0,
    )

    require_known_pricing: bool = False

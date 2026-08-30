"""Queries for discovering eligible language models."""

from pydantic import BaseModel, ConfigDict, Field

from azathoth.providers.models import (
    ModelCapability,
    ModelMetadata,
    ModelModality,
)
from azathoth.providers.requirements import ModelRequirements


class ModelQuery(BaseModel):
    """Requirements used to discover eligible language models."""

    model_config = ConfigDict(frozen=True)

    providers: frozenset[str] = frozenset()
    required_capabilities: frozenset[ModelCapability] = frozenset()
    required_input_modalities: frozenset[ModelModality] = frozenset()
    required_output_modalities: frozenset[ModelModality] = frozenset()

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

    def matches(
        self,
        model: ModelMetadata,
    ) -> bool:
        """Return whether a model satisfies every configured requirement."""

        if self.providers and model.provider not in self.providers:
            return False

        if not self.required_capabilities.issubset(model.capabilities):
            return False

        if not self.required_input_modalities.issubset(model.input_modalities):
            return False

        if not self.required_output_modalities.issubset(model.output_modalities):
            return False

        if self.minimum_context_window_tokens is not None:
            if model.context_window_tokens is None:
                return False

            if model.context_window_tokens < self.minimum_context_window_tokens:
                return False

        if self.minimum_output_tokens is not None:
            if model.maximum_output_tokens is None:
                return False

            if model.maximum_output_tokens < self.minimum_output_tokens:
                return False

        pricing_constraints_present = (
            self.maximum_input_usd_per_million_tokens is not None
            or self.maximum_output_usd_per_million_tokens is not None
        )

        if (self.require_known_pricing or pricing_constraints_present) and model.pricing is None:
            return False

        if model.pricing is not None:
            if (
                self.maximum_input_usd_per_million_tokens is not None
                and model.pricing.input_usd_per_million_tokens
                > self.maximum_input_usd_per_million_tokens
            ):
                return False

            if (
                self.maximum_output_usd_per_million_tokens is not None
                and model.pricing.output_usd_per_million_tokens
                > self.maximum_output_usd_per_million_tokens
            ):
                return False

        return True

    @classmethod
    def from_requirements(
        cls,
        requirements: ModelRequirements,
        *,
        providers: frozenset[str] = frozenset(),
    ) -> "ModelQuery":
        """Build a catalog query from workload model requirements."""

        return cls(
            providers=providers,
            required_capabilities=requirements.required_capabilities,
            required_input_modalities=requirements.required_input_modalities,
            required_output_modalities=requirements.required_output_modalities,
            minimum_context_window_tokens=(requirements.minimum_context_window_tokens),
            minimum_output_tokens=requirements.minimum_output_tokens,
            maximum_input_usd_per_million_tokens=(
                requirements.maximum_input_usd_per_million_tokens
            ),
            maximum_output_usd_per_million_tokens=(
                requirements.maximum_output_usd_per_million_tokens
            ),
            require_known_pricing=requirements.require_known_pricing,
        )

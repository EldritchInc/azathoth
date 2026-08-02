"""Tests for language model discovery queries."""

import pytest
from pydantic import ValidationError

from azathoth.providers import (
    ModelCapability,
    ModelMetadata,
    ModelModality,
    ModelPricing,
    ModelQuery,
    ModelRequirements,
)


def create_model(
    *,
    provider: str = "provider-a",
    model: str = "model-a",
    capabilities: frozenset[ModelCapability] = frozenset(),
    input_modalities: frozenset[ModelModality] = frozenset({ModelModality.TEXT}),
    output_modalities: frozenset[ModelModality] = frozenset({ModelModality.TEXT}),
    context_window_tokens: int = 128_000,
    maximum_output_tokens: int | None = 8_192,
    pricing: ModelPricing | None = None,
) -> ModelMetadata:
    """Create configurable model metadata for query tests."""

    return ModelMetadata(
        provider=provider,
        model=model,
        display_name=f"{provider} {model}",
        capabilities=capabilities,
        input_modalities=input_modalities,
        output_modalities=output_modalities,
        context_window_tokens=context_window_tokens,
        maximum_output_tokens=maximum_output_tokens,
        pricing=pricing,
    )


def test_empty_query_matches_any_model() -> None:
    query = ModelQuery()

    assert query.matches(create_model()) is True


def test_query_filters_by_provider() -> None:
    query = ModelQuery(
        providers=frozenset({"provider-b"}),
    )

    assert query.matches(create_model(provider="provider-b")) is True
    assert query.matches(create_model(provider="provider-a")) is False


def test_query_requires_all_capabilities() -> None:
    query = ModelQuery(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
                ModelCapability.TOOL_USE,
            }
        ),
    )

    complete = create_model(
        capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
                ModelCapability.TOOL_USE,
                ModelCapability.STREAMING,
            }
        )
    )
    incomplete = create_model(
        capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        )
    )

    assert query.matches(complete) is True
    assert query.matches(incomplete) is False


def test_query_requires_input_modalities() -> None:
    query = ModelQuery(
        required_input_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.IMAGE,
            }
        )
    )

    multimodal = create_model(
        input_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.IMAGE,
            }
        )
    )
    text_only = create_model()

    assert query.matches(multimodal) is True
    assert query.matches(text_only) is False


def test_query_requires_output_modalities() -> None:
    query = ModelQuery(
        required_output_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.AUDIO,
            }
        )
    )

    audio_output = create_model(
        output_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.AUDIO,
            }
        )
    )

    assert query.matches(audio_output) is True
    assert query.matches(create_model()) is False


def test_query_enforces_minimum_context_window() -> None:
    query = ModelQuery(
        minimum_context_window_tokens=100_000,
    )

    assert query.matches(create_model(context_window_tokens=128_000)) is True
    assert query.matches(create_model(context_window_tokens=32_000)) is False


def test_query_enforces_minimum_output_tokens() -> None:
    query = ModelQuery(
        minimum_output_tokens=8_000,
    )

    assert query.matches(create_model(maximum_output_tokens=16_000)) is True
    assert query.matches(create_model(maximum_output_tokens=4_000)) is False
    assert query.matches(create_model(maximum_output_tokens=None)) is False


def test_query_can_require_known_pricing() -> None:
    query = ModelQuery(
        require_known_pricing=True,
    )

    priced = create_model(
        pricing=ModelPricing(
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=4.0,
        )
    )

    assert query.matches(priced) is True
    assert query.matches(create_model(pricing=None)) is False


def test_query_enforces_input_and_output_price_limits() -> None:
    query = ModelQuery(
        maximum_input_usd_per_million_tokens=2.0,
        maximum_output_usd_per_million_tokens=8.0,
    )

    affordable = create_model(
        pricing=ModelPricing(
            input_usd_per_million_tokens=1.5,
            output_usd_per_million_tokens=7.0,
        )
    )
    expensive_input = create_model(
        pricing=ModelPricing(
            input_usd_per_million_tokens=3.0,
            output_usd_per_million_tokens=7.0,
        )
    )
    expensive_output = create_model(
        pricing=ModelPricing(
            input_usd_per_million_tokens=1.5,
            output_usd_per_million_tokens=10.0,
        )
    )

    assert query.matches(affordable) is True
    assert query.matches(expensive_input) is False
    assert query.matches(expensive_output) is False


def test_pricing_constraint_excludes_unknown_pricing() -> None:
    query = ModelQuery(
        maximum_input_usd_per_million_tokens=2.0,
    )

    assert query.matches(create_model(pricing=None)) is False


def test_query_rejects_invalid_numeric_requirements() -> None:
    with pytest.raises(ValidationError):
        ModelQuery(
            minimum_context_window_tokens=0,
        )

    with pytest.raises(ValidationError):
        ModelQuery(
            maximum_input_usd_per_million_tokens=-1.0,
        )


def test_model_query_round_trips_through_json() -> None:
    query = ModelQuery(
        providers=frozenset(
            {
                "provider-a",
                "provider-b",
            }
        ),
        required_capabilities=frozenset(
            {
                ModelCapability.TOOL_USE,
            }
        ),
        required_input_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.IMAGE,
            }
        ),
        minimum_context_window_tokens=100_000,
        maximum_input_usd_per_million_tokens=2.0,
        require_known_pricing=True,
    )

    restored = ModelQuery.model_validate_json(query.model_dump_json())

    assert restored == query


def test_query_builds_from_model_requirements() -> None:
    requirements = ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
                ModelCapability.TOOL_USE,
            }
        ),
        required_input_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.IMAGE,
            }
        ),
        required_output_modalities=frozenset(
            {
                ModelModality.TEXT,
            }
        ),
        minimum_context_window_tokens=100_000,
        minimum_output_tokens=8_000,
        maximum_input_usd_per_million_tokens=2.0,
        maximum_output_usd_per_million_tokens=8.0,
        require_known_pricing=True,
    )

    query = ModelQuery.from_requirements(requirements)

    assert query.providers == frozenset()
    assert query.required_capabilities == requirements.required_capabilities
    assert query.required_input_modalities == requirements.required_input_modalities
    assert query.required_output_modalities == requirements.required_output_modalities
    assert query.minimum_context_window_tokens == requirements.minimum_context_window_tokens
    assert query.minimum_output_tokens == requirements.minimum_output_tokens
    assert (
        query.maximum_input_usd_per_million_tokens
        == requirements.maximum_input_usd_per_million_tokens
    )
    assert (
        query.maximum_output_usd_per_million_tokens
        == requirements.maximum_output_usd_per_million_tokens
    )
    assert query.require_known_pricing is True


def test_query_from_requirements_accepts_provider_restrictions() -> None:
    requirements = ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.TOOL_USE,
            }
        ),
    )

    query = ModelQuery.from_requirements(
        requirements,
        providers=frozenset(
            {
                "provider-a",
                "provider-b",
            }
        ),
    )

    assert query.providers == frozenset(
        {
            "provider-a",
            "provider-b",
        }
    )
    assert query.required_capabilities == frozenset(
        {
            ModelCapability.TOOL_USE,
        }
    )


def test_query_from_default_requirements_preserves_text_modalities() -> None:
    query = ModelQuery.from_requirements(ModelRequirements())

    assert query.required_input_modalities == frozenset(
        {
            ModelModality.TEXT,
        }
    )
    assert query.required_output_modalities == frozenset(
        {
            ModelModality.TEXT,
        }
    )

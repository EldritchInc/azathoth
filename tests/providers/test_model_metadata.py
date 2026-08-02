"""Tests for configured language model metadata."""

import pytest
from pydantic import ValidationError

from azathoth.providers import (
    ModelCapability,
    ModelMetadata,
    ModelModality,
    ModelPricing,
)


def create_metadata() -> ModelMetadata:
    """Create deterministic metadata for provider tests."""

    return ModelMetadata(
        provider="example-provider",
        model="reasoning-large",
        display_name="Reasoning Large",
        input_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.IMAGE,
            }
        ),
        output_modalities=frozenset(
            {
                ModelModality.TEXT,
            }
        ),
        capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
                ModelCapability.TOOL_USE,
                ModelCapability.VISION,
            }
        ),
        context_window_tokens=200_000,
        maximum_output_tokens=16_000,
        pricing=ModelPricing(
            input_usd_per_million_tokens=2.50,
            output_usd_per_million_tokens=10.00,
        ),
    )


def test_model_metadata_records_identity_and_capabilities() -> None:
    metadata = create_metadata()

    assert metadata.identifier == "example-provider/reasoning-large"
    assert ModelCapability.TOOL_USE in metadata.capabilities
    assert ModelModality.IMAGE in metadata.input_modalities
    assert metadata.context_window_tokens == 200_000


def test_model_metadata_defaults_to_text_input_and_output() -> None:
    metadata = ModelMetadata(
        provider="local",
        model="small",
        display_name="Local Small",
        context_window_tokens=8_192,
    )

    assert metadata.input_modalities == frozenset({ModelModality.TEXT})
    assert metadata.output_modalities == frozenset({ModelModality.TEXT})
    assert metadata.capabilities == frozenset()


def test_model_metadata_allows_unknown_pricing() -> None:
    metadata = ModelMetadata(
        provider="internal",
        model="experimental",
        display_name="Experimental",
        context_window_tokens=32_000,
    )

    assert metadata.pricing is None


def test_model_metadata_is_immutable() -> None:
    metadata = create_metadata()

    with pytest.raises(ValidationError):
        metadata.model = "changed"


def test_model_metadata_rejects_invalid_context_window() -> None:
    with pytest.raises(ValidationError):
        ModelMetadata(
            provider="test",
            model="invalid",
            display_name="Invalid",
            context_window_tokens=0,
        )


def test_model_pricing_rejects_negative_values() -> None:
    with pytest.raises(ValidationError):
        ModelPricing(
            input_usd_per_million_tokens=-1.0,
            output_usd_per_million_tokens=1.0,
        )


def test_model_metadata_round_trips_through_json() -> None:
    metadata = create_metadata()

    restored = ModelMetadata.model_validate_json(metadata.model_dump_json())

    assert restored == metadata

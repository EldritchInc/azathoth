"""Tests for deriving runtime metadata from current provider model state."""

from azathoth.providers import (
    ModelCapability,
    ModelModality,
    ModelPricing,
    ProviderModel,
    model_metadata_from_provider_model,
)


def test_provider_model_derives_runtime_metadata() -> None:
    pricing = ModelPricing(
        input_usd_per_million_tokens=1.25,
        output_usd_per_million_tokens=5.0,
    )

    provider_model = ProviderModel(
        provider="example-provider",
        model="example/model",
        display_name="Example Model",
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
        context_window_tokens=128_000,
        maximum_output_tokens=16_384,
        pricing=pricing,
    )

    metadata = model_metadata_from_provider_model(provider_model)

    assert metadata.provider == "example-provider"
    assert metadata.model == "example/model"
    assert metadata.display_name == "Example Model"

    assert metadata.input_modalities == frozenset(
        {
            ModelModality.TEXT,
            ModelModality.IMAGE,
        }
    )

    assert metadata.output_modalities == frozenset(
        {
            ModelModality.TEXT,
        }
    )

    assert metadata.capabilities == frozenset(
        {
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.TOOL_USE,
            ModelCapability.VISION,
        }
    )

    assert metadata.context_window_tokens == 128_000
    assert metadata.maximum_output_tokens == 16_384
    assert metadata.pricing == pricing

    assert metadata.identifier == provider_model.identifier


def test_provider_model_preserves_unknown_runtime_metadata() -> None:
    provider_model = ProviderModel(
        provider="example-provider",
        model="unknown-limits",
        display_name="Unknown Limits",
        context_window_tokens=None,
        maximum_output_tokens=None,
        pricing=None,
    )

    metadata = model_metadata_from_provider_model(provider_model)

    assert metadata.context_window_tokens is None
    assert metadata.maximum_output_tokens is None
    assert metadata.pricing is None

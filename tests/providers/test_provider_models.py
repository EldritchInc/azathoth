"""Tests for provider-sourced model state and observations."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.providers import (
    ModelCapability,
    ModelModality,
    ModelPricing,
    ProviderModel,
    ProviderModelObservation,
)

OBSERVATION_ID = UUID("11111111-1111-1111-1111-111111111111")

OBSERVED_AT = datetime(
    2026,
    8,
    24,
    20,
    0,
    0,
    tzinfo=UTC,
)


def create_provider_model() -> ProviderModel:
    """Create one deterministic provider model."""

    return ProviderModel(
        provider="example",
        model="frontier",
        display_name="Frontier Model",
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
        pricing=ModelPricing(
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=4.0,
        ),
    )


def test_provider_model_exposes_provider_qualified_identifier() -> None:
    model = create_provider_model()

    assert model.identifier == "example/frontier"


def test_provider_model_defaults_to_text_modalities() -> None:
    model = ProviderModel(
        provider="example",
        model="text",
        display_name="Text Model",
        context_window_tokens=8_192,
    )

    assert model.input_modalities == frozenset(
        {
            ModelModality.TEXT,
        }
    )

    assert model.output_modalities == frozenset(
        {
            ModelModality.TEXT,
        }
    )

    assert model.capabilities == frozenset()
    assert model.maximum_output_tokens is None
    assert model.pricing is None


def test_provider_model_fingerprint_is_deterministic() -> None:
    first = create_provider_model()
    second = create_provider_model()

    assert first.fingerprint == second.fingerprint


def test_provider_model_fingerprint_changes_when_provider_facts_change() -> None:
    original = create_provider_model()

    changed = original.model_copy(
        update={
            "context_window_tokens": 256_000,
        }
    )

    assert original.fingerprint != changed.fingerprint


def test_provider_model_fingerprint_changes_when_pricing_changes() -> None:
    original = create_provider_model()

    changed = original.model_copy(
        update={
            "pricing": ModelPricing(
                input_usd_per_million_tokens=0.5,
                output_usd_per_million_tokens=2.0,
            ),
        }
    )

    assert original.fingerprint != changed.fingerprint


def test_provider_model_fingerprint_changes_when_capabilities_change() -> None:
    original = create_provider_model()

    changed = original.model_copy(
        update={
            "capabilities": frozenset(
                {
                    ModelCapability.STRUCTURED_OUTPUT,
                    ModelCapability.TOOL_USE,
                }
            ),
        }
    )

    assert original.fingerprint != changed.fingerprint


def test_provider_model_observation_records_model_and_time() -> None:
    model = create_provider_model()

    observation = ProviderModelObservation(
        id=OBSERVATION_ID,
        observed_at=OBSERVED_AT,
        model=model,
    )

    assert observation.id == OBSERVATION_ID
    assert observation.observed_at == OBSERVED_AT
    assert observation.model is model


def test_provider_model_observation_exposes_model_identity() -> None:
    observation = ProviderModelObservation(
        id=OBSERVATION_ID,
        observed_at=OBSERVED_AT,
        model=create_provider_model(),
    )

    assert observation.provider == "example"
    assert observation.model_identifier == "frontier"
    assert observation.identifier == "example/frontier"


def test_provider_model_observation_exposes_provider_fingerprint() -> None:
    model = create_provider_model()

    observation = ProviderModelObservation(
        id=OBSERVATION_ID,
        observed_at=OBSERVED_AT,
        model=model,
    )

    assert observation.fingerprint == model.fingerprint


def test_observation_identity_does_not_change_provider_fingerprint() -> None:
    model = create_provider_model()

    first = ProviderModelObservation(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        observed_at=datetime(
            2026,
            8,
            24,
            20,
            0,
            0,
            tzinfo=UTC,
        ),
        model=model,
    )

    second = ProviderModelObservation(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        observed_at=datetime(
            2026,
            8,
            25,
            20,
            0,
            0,
            tzinfo=UTC,
        ),
        model=model,
    )

    assert first.id != second.id
    assert first.observed_at != second.observed_at

    assert first.fingerprint == second.fingerprint


def test_provider_model_and_observation_are_immutable() -> None:
    model = create_provider_model()

    observation = ProviderModelObservation(model=model)

    assert model.model_config["frozen"]
    assert observation.model_config["frozen"]


def test_provider_model_allows_unknown_token_limits() -> None:
    model = ProviderModel(
        provider="example",
        model="non-token-model",
        display_name="Non-Token Model",
    )

    assert model.context_window_tokens is None
    assert model.maximum_output_tokens is None

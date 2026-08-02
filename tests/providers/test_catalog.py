"""Tests for the immutable language model catalog."""

import pytest
from pydantic import ValidationError

from azathoth.providers import (
    ModelCapability,
    ModelCatalog,
    ModelMetadata,
    ModelModality,
    ModelPricing,
    ModelQuery,
    ModelRequirements,
)


def create_model(
    *,
    provider: str,
    model: str,
    display_name: str,
) -> ModelMetadata:
    """Create deterministic metadata for catalog tests."""

    return ModelMetadata(
        provider=provider,
        model=model,
        display_name=display_name,
        capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        input_modalities=frozenset(
            {
                ModelModality.TEXT,
            }
        ),
        output_modalities=frozenset(
            {
                ModelModality.TEXT,
            }
        ),
        context_window_tokens=128_000,
        maximum_output_tokens=8_192,
        pricing=ModelPricing(
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=4.0,
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create a deterministic model catalog."""

    return ModelCatalog(
        models=(
            create_model(
                provider="provider-a",
                model="small",
                display_name="Provider A Small",
            ),
            create_model(
                provider="provider-a",
                model="large",
                display_name="Provider A Large",
            ),
            create_model(
                provider="provider-b",
                model="reasoning",
                display_name="Provider B Reasoning",
            ),
        )
    )


def test_catalog_preserves_model_order() -> None:
    catalog = create_catalog()

    assert catalog.identifiers == (
        "provider-a/small",
        "provider-a/large",
        "provider-b/reasoning",
    )


def test_catalog_returns_model_by_identifier() -> None:
    catalog = create_catalog()

    model = catalog.get("provider-a/large")

    assert model is not None
    assert model.display_name == "Provider A Large"


def test_catalog_returns_none_for_unknown_identifier() -> None:
    catalog = create_catalog()

    assert catalog.get("provider-c/missing") is None


def test_catalog_returns_models_for_provider() -> None:
    catalog = create_catalog()

    models = catalog.models_for_provider("provider-a")

    assert tuple(model.identifier for model in models) == (
        "provider-a/small",
        "provider-a/large",
    )


def test_catalog_returns_empty_tuple_for_unknown_provider() -> None:
    catalog = create_catalog()

    assert catalog.models_for_provider("unknown") == ()


def test_catalog_lists_providers_in_first_seen_order() -> None:
    catalog = create_catalog()

    assert catalog.providers == (
        "provider-a",
        "provider-b",
    )


def test_catalog_allows_empty_inventory() -> None:
    catalog = ModelCatalog()

    assert catalog.models == ()
    assert catalog.identifiers == ()
    assert catalog.providers == ()


def test_catalog_rejects_duplicate_identifiers() -> None:
    first = create_model(
        provider="provider-a",
        model="small",
        display_name="First Name",
    )
    duplicate = create_model(
        provider="provider-a",
        model="small",
        display_name="Different Display Name",
    )

    with pytest.raises(
        ValidationError,
        match="duplicate model identifiers",
    ):
        ModelCatalog(
            models=(
                first,
                duplicate,
            )
        )


def test_same_model_name_is_allowed_across_providers() -> None:
    catalog = ModelCatalog(
        models=(
            create_model(
                provider="provider-a",
                model="small",
                display_name="Provider A Small",
            ),
            create_model(
                provider="provider-b",
                model="small",
                display_name="Provider B Small",
            ),
        )
    )

    assert catalog.identifiers == (
        "provider-a/small",
        "provider-b/small",
    )


def test_catalog_is_immutable() -> None:
    catalog = create_catalog()

    with pytest.raises(ValidationError):
        catalog.models = ()


def test_catalog_round_trips_through_json() -> None:
    catalog = create_catalog()

    restored = ModelCatalog.model_validate_json(catalog.model_dump_json())

    assert restored == catalog


def test_catalog_finds_models_matching_query() -> None:
    catalog = create_catalog()

    models = catalog.find(
        ModelQuery(
            providers=frozenset({"provider-a"}),
            required_capabilities=frozenset(
                {
                    ModelCapability.STRUCTURED_OUTPUT,
                }
            ),
            minimum_context_window_tokens=100_000,
        )
    )

    assert tuple(model.identifier for model in models) == (
        "provider-a/small",
        "provider-a/large",
    )


def test_catalog_find_preserves_catalog_order() -> None:
    catalog = create_catalog()

    models = catalog.find(ModelQuery())

    assert tuple(model.identifier for model in models) == (
        "provider-a/small",
        "provider-a/large",
        "provider-b/reasoning",
    )


def test_catalog_find_returns_empty_tuple_when_nothing_matches() -> None:
    catalog = create_catalog()

    models = catalog.find(
        ModelQuery(
            required_capabilities=frozenset(
                {
                    ModelCapability.TOOL_USE,
                }
            )
        )
    )

    assert models == ()


def test_catalog_finds_models_from_workload_requirements() -> None:
    catalog = create_catalog()

    requirements = ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        minimum_context_window_tokens=100_000,
        maximum_input_usd_per_million_tokens=2.0,
        require_known_pricing=True,
    )

    models = catalog.find(
        ModelQuery.from_requirements(
            requirements,
            providers=frozenset(
                {
                    "provider-a",
                }
            ),
        )
    )

    assert tuple(model.identifier for model in models) == (
        "provider-a/small",
        "provider-a/large",
    )

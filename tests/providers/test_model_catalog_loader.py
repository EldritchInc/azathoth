"""Tests for reconstruction of model catalogs from repositories."""

from azathoth.providers import (
    InMemoryModelRepository,
    ModelCapability,
    ModelCatalogLoader,
    ModelMetadata,
    ModelPricing,
)


def create_first_model() -> ModelMetadata:
    """Create deterministic first model metadata."""

    return ModelMetadata(
        provider="openrouter",
        model="example/cheap-model",
        display_name="Cheap Model",
        context_window_tokens=8_192,
        pricing=ModelPricing(
            input_usd_per_million_tokens=0.1,
            output_usd_per_million_tokens=0.1,
        ),
    )


def create_second_model() -> ModelMetadata:
    """Create deterministic second model metadata."""

    return ModelMetadata(
        provider="openrouter",
        model="example/structured-model",
        display_name="Structured Model",
        capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        context_window_tokens=32_768,
        pricing=ModelPricing(
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=1.0,
        ),
    )


def test_model_catalog_loader_reconstructs_repository_models() -> None:
    repository = InMemoryModelRepository()

    first = create_first_model()
    second = create_second_model()

    repository.save(first)
    repository.save(second)

    catalog = ModelCatalogLoader(repository).load_catalog()

    assert catalog.models == (
        first,
        second,
    )


def test_model_catalog_loader_preserves_repository_order() -> None:
    repository = InMemoryModelRepository()

    repository.save(create_second_model())
    repository.save(create_first_model())

    catalog = ModelCatalogLoader(repository).load_catalog()

    assert catalog.identifiers == (
        "openrouter/example/structured-model",
        "openrouter/example/cheap-model",
    )


def test_model_catalog_loader_returns_empty_catalog() -> None:
    catalog = ModelCatalogLoader(InMemoryModelRepository()).load_catalog()

    assert catalog.models == ()


def test_reconstructed_catalog_preserves_model_capabilities() -> None:
    repository = InMemoryModelRepository()

    model = create_second_model()

    repository.save(model)

    catalog = ModelCatalogLoader(repository).load_catalog()

    restored = catalog.get(model.identifier)

    assert restored == model

    assert restored is not None

    assert ModelCapability.STRUCTURED_OUTPUT in restored.capabilities

    assert restored.pricing is not None
    assert restored.pricing.input_usd_per_million_tokens == 1.0

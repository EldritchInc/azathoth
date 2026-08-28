"""Tests for synchronizing current provider model catalogs."""

import asyncio

from azathoth.providers import (
    InMemoryProviderModelObservationRepository,
    ModelCapability,
    ModelModality,
    ModelPricing,
    ProviderModel,
    ProviderModelCatalogSynchronizer,
    ProviderModelObserver,
)


class MutableProviderModelDirectory:
    """Provide deterministic mutable current provider state for tests."""

    def __init__(
        self,
        *,
        provider: str,
        models: tuple[ProviderModel, ...] = (),
    ) -> None:
        self._provider = provider
        self.models_state = models

    @property
    def provider(
        self,
    ) -> str:
        """Return the deterministic provider identifier."""

        return self._provider

    async def models(
        self,
    ) -> tuple[ProviderModel, ...]:
        """Return current deterministic provider state."""

        return self.models_state

    async def model(
        self,
        identifier: str,
    ) -> ProviderModel | None:
        """Return one current provider model by provider-native identity."""

        return next(
            (model for model in self.models_state if model.model == identifier),
            None,
        )


def create_model(
    *,
    provider: str = "provider-a",
    model: str = "model-a",
) -> ProviderModel:
    """Create deterministic provider model state."""

    return ProviderModel(
        provider=provider,
        model=model,
        display_name=model,
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
                ModelCapability.VISION,
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        context_window_tokens=128_000,
        maximum_output_tokens=16_384,
        pricing=ModelPricing(
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=4.0,
        ),
    )


def create_observer(
    directory: MutableProviderModelDirectory,
    repository: InMemoryProviderModelObservationRepository,
) -> ProviderModelObserver:
    """Create one deterministic provider observer."""

    return ProviderModelObserver(
        directory=directory,
        repository=repository,
    )


def test_synchronizer_builds_catalog_from_current_provider_state() -> None:
    first = create_model(
        model="first",
    )

    second = create_model(
        model="second",
    )

    directory = MutableProviderModelDirectory(
        provider="provider-a",
        models=(
            first,
            second,
        ),
    )

    repository = InMemoryProviderModelObservationRepository()

    synchronizer = ProviderModelCatalogSynchronizer(
        observers=(
            create_observer(
                directory,
                repository,
            ),
        )
    )

    catalog = asyncio.run(synchronizer.synchronize())

    assert catalog.identifiers == (
        "provider-a/first",
        "provider-a/second",
    )

    assert catalog.get("provider-a/first") is not None
    assert catalog.get("provider-a/second") is not None


def test_synchronizer_preserves_provider_metadata() -> None:
    provider_model = create_model()

    directory = MutableProviderModelDirectory(
        provider="provider-a",
        models=(provider_model,),
    )

    synchronizer = ProviderModelCatalogSynchronizer(
        observers=(
            create_observer(
                directory,
                InMemoryProviderModelObservationRepository(),
            ),
        )
    )

    catalog = asyncio.run(synchronizer.synchronize())

    metadata = catalog.get(provider_model.identifier)

    assert metadata is not None

    assert metadata.provider == provider_model.provider
    assert metadata.model == provider_model.model
    assert metadata.display_name == provider_model.display_name
    assert metadata.input_modalities == provider_model.input_modalities
    assert metadata.output_modalities == provider_model.output_modalities
    assert metadata.capabilities == provider_model.capabilities
    assert metadata.context_window_tokens == provider_model.context_window_tokens
    assert metadata.maximum_output_tokens == provider_model.maximum_output_tokens
    assert metadata.pricing == provider_model.pricing


def test_synchronizer_preserves_observer_and_provider_order() -> None:
    first_provider = MutableProviderModelDirectory(
        provider="provider-a",
        models=(
            create_model(
                provider="provider-a",
                model="second",
            ),
            create_model(
                provider="provider-a",
                model="first",
            ),
        ),
    )

    second_provider = MutableProviderModelDirectory(
        provider="provider-b",
        models=(
            create_model(
                provider="provider-b",
                model="third",
            ),
        ),
    )

    synchronizer = ProviderModelCatalogSynchronizer(
        observers=(
            create_observer(
                first_provider,
                InMemoryProviderModelObservationRepository(),
            ),
            create_observer(
                second_provider,
                InMemoryProviderModelObservationRepository(),
            ),
        )
    )

    catalog = asyncio.run(synchronizer.synchronize())

    assert catalog.identifiers == (
        "provider-a/second",
        "provider-a/first",
        "provider-b/third",
    )


def test_synchronizer_excludes_models_removed_from_current_provider_state() -> None:
    removed = create_model(
        model="removed",
    )

    remaining = create_model(
        model="remaining",
    )

    directory = MutableProviderModelDirectory(
        provider="provider-a",
        models=(
            removed,
            remaining,
        ),
    )

    repository = InMemoryProviderModelObservationRepository()

    synchronizer = ProviderModelCatalogSynchronizer(
        observers=(
            create_observer(
                directory,
                repository,
            ),
        )
    )

    first_catalog = asyncio.run(synchronizer.synchronize())

    assert first_catalog.identifiers == (
        "provider-a/removed",
        "provider-a/remaining",
    )

    assert repository.latest(removed.identifier) is not None

    directory.models_state = (remaining,)

    second_catalog = asyncio.run(synchronizer.synchronize())

    assert second_catalog.identifiers == ("provider-a/remaining",)

    assert repository.latest(removed.identifier) is not None


def test_synchronizer_records_changed_current_provider_state() -> None:
    initial = create_model()

    directory = MutableProviderModelDirectory(
        provider="provider-a",
        models=(initial,),
    )

    repository = InMemoryProviderModelObservationRepository()

    synchronizer = ProviderModelCatalogSynchronizer(
        observers=(
            create_observer(
                directory,
                repository,
            ),
        )
    )

    asyncio.run(synchronizer.synchronize())

    changed = initial.model_copy(
        update={
            "context_window_tokens": 256_000,
        }
    )

    directory.models_state = (changed,)

    catalog = asyncio.run(synchronizer.synchronize())

    assert len(repository.observations_for_model(initial.identifier)) == 2

    metadata = catalog.get(changed.identifier)

    assert metadata is not None
    assert metadata.context_window_tokens == 256_000


def test_synchronizer_reuses_unchanged_observation() -> None:
    model = create_model()

    directory = MutableProviderModelDirectory(
        provider="provider-a",
        models=(model,),
    )

    repository = InMemoryProviderModelObservationRepository()

    synchronizer = ProviderModelCatalogSynchronizer(
        observers=(
            create_observer(
                directory,
                repository,
            ),
        )
    )

    first = asyncio.run(synchronizer.synchronize())
    second = asyncio.run(synchronizer.synchronize())

    assert first == second

    assert len(repository.observations_for_model(model.identifier)) == 1


def test_synchronizer_rejects_duplicate_current_model_identities() -> None:
    first_directory = MutableProviderModelDirectory(
        provider="provider-a",
        models=(
            create_model(
                provider="provider-a",
                model="duplicate",
            ),
        ),
    )

    second_directory = MutableProviderModelDirectory(
        provider="provider-a",
        models=(
            create_model(
                provider="provider-a",
                model="duplicate",
            ),
        ),
    )

    synchronizer = ProviderModelCatalogSynchronizer(
        observers=(
            create_observer(
                first_directory,
                InMemoryProviderModelObservationRepository(),
            ),
            create_observer(
                second_directory,
                InMemoryProviderModelObservationRepository(),
            ),
        )
    )

    try:
        asyncio.run(synchronizer.synchronize())
    except ValueError as exc:
        assert str(exc) == (
            "Current provider model 'provider-a/duplicate' was discovered more than once."
        )
    else:
        raise AssertionError("Duplicate current provider model identity was accepted.")

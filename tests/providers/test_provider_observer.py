"""Tests for provider model observation change detection."""

import asyncio

import pytest

from azathoth.providers import (
    InMemoryProviderModelObservationRepository,
    ModelCapability,
    ModelPricing,
    ProviderModel,
    ProviderModelObserver,
)


class ExampleProviderModelDirectory:
    """Mutable deterministic directory for observer tests."""

    def __init__(
        self,
        *,
        provider: str = "example",
        models: tuple[
            ProviderModel,
            ...,
        ] = (),
    ) -> None:
        self._provider = provider
        self._models = models

    @property
    def provider(
        self,
    ) -> str:
        """Return the directory provider."""

        return self._provider

    async def models(
        self,
    ) -> tuple[
        ProviderModel,
        ...,
    ]:
        """Return current deterministic model state."""

        return self._models

    async def model(
        self,
        identifier: str,
    ) -> ProviderModel | None:
        """Return one model by provider-native identifier."""

        return next(
            (model for model in self._models if model.model == identifier),
            None,
        )

    def replace_models(
        self,
        models: tuple[
            ProviderModel,
            ...,
        ],
    ) -> None:
        """Replace deterministic provider state."""

        self._models = models


def create_provider_model(
    *,
    model: str = "frontier",
    context_window_tokens: int = 128_000,
    input_price: float = 1.0,
    output_price: float = 4.0,
    capabilities: frozenset[ModelCapability] = frozenset(),
    provider: str = "example",
) -> ProviderModel:
    """Create deterministic provider model state."""

    return ProviderModel(
        provider=provider,
        model=model,
        display_name=model.title(),
        capabilities=capabilities,
        context_window_tokens=context_window_tokens,
        pricing=ModelPricing(
            input_usd_per_million_tokens=input_price,
            output_usd_per_million_tokens=output_price,
        ),
    )


def test_observe_model_records_first_provider_state() -> None:
    model = create_provider_model()

    directory = ExampleProviderModelDirectory(models=(model,))

    repository = InMemoryProviderModelObservationRepository()

    observer = ProviderModelObserver(
        directory=directory,
        repository=repository,
    )

    update = asyncio.run(observer.observe_model("frontier"))

    assert update is not None
    assert update.created
    assert update.observation.model == model

    assert repository.observations() == (update.observation,)


def test_observe_model_reuses_latest_observation_when_state_is_unchanged() -> None:
    model = create_provider_model()

    directory = ExampleProviderModelDirectory(models=(model,))

    repository = InMemoryProviderModelObservationRepository()

    observer = ProviderModelObserver(
        directory=directory,
        repository=repository,
    )

    first = asyncio.run(observer.observe_model("frontier"))

    second = asyncio.run(observer.observe_model("frontier"))

    assert first is not None
    assert second is not None

    assert first.created
    assert not second.created

    assert second.observation is first.observation

    assert repository.observations() == (first.observation,)


def test_observe_model_records_changed_provider_state() -> None:
    original = create_provider_model(
        input_price=1.0,
        output_price=4.0,
    )

    changed = create_provider_model(
        input_price=0.5,
        output_price=2.0,
    )

    directory = ExampleProviderModelDirectory(models=(original,))

    repository = InMemoryProviderModelObservationRepository()

    observer = ProviderModelObserver(
        directory=directory,
        repository=repository,
    )

    first = asyncio.run(observer.observe_model("frontier"))

    directory.replace_models((changed,))

    second = asyncio.run(observer.observe_model("frontier"))

    assert first is not None
    assert second is not None

    assert first.created
    assert second.created

    assert first.observation.fingerprint != second.observation.fingerprint

    assert repository.observations() == (
        first.observation,
        second.observation,
    )


def test_observe_model_detects_capability_change() -> None:
    original = create_provider_model()

    changed = create_provider_model(
        capabilities=frozenset(
            {
                ModelCapability.TOOL_USE,
            }
        )
    )

    directory = ExampleProviderModelDirectory(models=(original,))

    repository = InMemoryProviderModelObservationRepository()

    observer = ProviderModelObserver(
        directory=directory,
        repository=repository,
    )

    first = asyncio.run(observer.observe_model("frontier"))

    directory.replace_models((changed,))

    second = asyncio.run(observer.observe_model("frontier"))

    assert first is not None
    assert second is not None

    assert first.created
    assert second.created

    assert len(repository.observations()) == 2


def test_observe_model_detects_context_window_change() -> None:
    original = create_provider_model(context_window_tokens=128_000)

    changed = create_provider_model(context_window_tokens=256_000)

    directory = ExampleProviderModelDirectory(models=(original,))

    repository = InMemoryProviderModelObservationRepository()

    observer = ProviderModelObserver(
        directory=directory,
        repository=repository,
    )

    asyncio.run(observer.observe_model("frontier"))

    directory.replace_models((changed,))

    update = asyncio.run(observer.observe_model("frontier"))

    assert update is not None
    assert update.created

    assert len(repository.observations()) == 2


def test_observe_model_returns_none_for_unknown_model() -> None:
    observer = ProviderModelObserver(
        directory=ExampleProviderModelDirectory(),
        repository=(InMemoryProviderModelObservationRepository()),
    )

    update = asyncio.run(observer.observe_model("missing"))

    assert update is None


def test_observe_model_rejects_mismatched_provider() -> None:
    observer = ProviderModelObserver(
        directory=ExampleProviderModelDirectory(
            provider="example",
            models=(
                create_provider_model(
                    provider="other",
                ),
            ),
        ),
        repository=(InMemoryProviderModelObservationRepository()),
    )

    with pytest.raises(
        ValueError,
        match=("Provider model directory 'example' returned model 'other/frontier'"),
    ):
        asyncio.run(observer.observe_model("frontier"))


def test_observe_models_records_complete_provider_directory() -> None:
    first_model = create_provider_model(model="alpha")

    second_model = create_provider_model(model="beta")

    repository = InMemoryProviderModelObservationRepository()

    observer = ProviderModelObserver(
        directory=ExampleProviderModelDirectory(
            models=(
                first_model,
                second_model,
            )
        ),
        repository=repository,
    )

    updates = asyncio.run(observer.observe_models())

    assert len(updates) == 2

    assert all(update.created for update in updates)

    assert tuple(update.observation.model for update in updates) == (
        first_model,
        second_model,
    )

    assert len(repository.observations()) == 2


def test_observe_models_only_records_changed_models() -> None:
    alpha = create_provider_model(
        model="alpha",
        input_price=1.0,
        output_price=4.0,
    )

    beta = create_provider_model(
        model="beta",
        input_price=2.0,
        output_price=8.0,
    )

    directory = ExampleProviderModelDirectory(
        models=(
            alpha,
            beta,
        )
    )

    repository = InMemoryProviderModelObservationRepository()

    observer = ProviderModelObserver(
        directory=directory,
        repository=repository,
    )

    first_poll = asyncio.run(observer.observe_models())

    changed_beta = create_provider_model(
        model="beta",
        input_price=1.5,
        output_price=6.0,
    )

    directory.replace_models(
        (
            alpha,
            changed_beta,
        )
    )

    second_poll = asyncio.run(observer.observe_models())

    assert tuple(update.created for update in first_poll) == (
        True,
        True,
    )

    assert tuple(update.created for update in second_poll) == (
        False,
        True,
    )

    assert len(repository.observations()) == 3

    assert len(repository.observations_for_model("example/alpha")) == 1

    assert len(repository.observations_for_model("example/beta")) == 2


def test_observe_models_validates_all_models_before_persisting() -> None:
    valid = create_provider_model(model="alpha")

    invalid = create_provider_model(
        provider="other",
        model="beta",
    )

    repository = InMemoryProviderModelObservationRepository()

    observer = ProviderModelObserver(
        directory=ExampleProviderModelDirectory(
            models=(
                valid,
                invalid,
            )
        ),
        repository=repository,
    )

    with pytest.raises(
        ValueError,
        match=("Provider model directory 'example' returned model 'other/beta'"),
    ):
        asyncio.run(observer.observe_models())

    assert repository.observations() == ()


def test_observe_models_rejects_duplicate_identifiers_before_persisting() -> None:
    model = create_provider_model(model="alpha")

    repository = InMemoryProviderModelObservationRepository()

    observer = ProviderModelObserver(
        directory=ExampleProviderModelDirectory(
            models=(
                model,
                model,
            )
        ),
        repository=repository,
    )

    with pytest.raises(
        ValueError,
        match=("Provider model directory cannot return duplicate model identifiers"),
    ):
        asyncio.run(observer.observe_models())

    assert repository.observations() == ()

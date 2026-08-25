"""Tests for provider model observation persistence."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.providers import (
    InMemoryProviderModelObservationRepository,
    ModelPricing,
    ProviderModel,
    ProviderModelObservation,
    ProviderModelObservationRepository,
    require_provider_model_observation_repository,
)

FIRST_OBSERVATION_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_OBSERVATION_ID = UUID("22222222-2222-2222-2222-222222222222")

OTHER_OBSERVATION_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_OBSERVED_AT = datetime(
    2026,
    8,
    24,
    20,
    0,
    0,
    tzinfo=UTC,
)

SECOND_OBSERVED_AT = datetime(
    2026,
    8,
    24,
    21,
    0,
    0,
    tzinfo=UTC,
)


def create_provider_model(
    *,
    price: float = 1.0,
) -> ProviderModel:
    """Create deterministic provider model state."""

    return ProviderModel(
        provider="example",
        model="frontier",
        display_name="Frontier Model",
        context_window_tokens=128_000,
        pricing=ModelPricing(
            input_usd_per_million_tokens=price,
            output_usd_per_million_tokens=price * 4,
        ),
    )


def create_first_observation() -> ProviderModelObservation:
    """Create the first deterministic observation."""

    return ProviderModelObservation(
        id=FIRST_OBSERVATION_ID,
        observed_at=FIRST_OBSERVED_AT,
        model=create_provider_model(),
    )


def create_second_observation() -> ProviderModelObservation:
    """Create a changed observation for the same model."""

    return ProviderModelObservation(
        id=SECOND_OBSERVATION_ID,
        observed_at=SECOND_OBSERVED_AT,
        model=create_provider_model(price=0.5),
    )


def create_other_observation() -> ProviderModelObservation:
    """Create an observation for another model."""

    return ProviderModelObservation(
        id=OTHER_OBSERVATION_ID,
        observed_at=SECOND_OBSERVED_AT,
        model=ProviderModel(
            provider="example",
            model="other",
            display_name="Other Model",
            context_window_tokens=8_192,
        ),
    )


def test_memory_observation_repository_satisfies_protocol() -> None:
    repository = InMemoryProviderModelObservationRepository()

    resolved = require_provider_model_observation_repository(repository)

    assert resolved is repository


def test_memory_observation_repository_persists_observation() -> None:
    repository: ProviderModelObservationRepository = InMemoryProviderModelObservationRepository()

    observation = create_first_observation()

    repository.save(observation)

    assert repository.get(observation.id) == observation


def test_memory_observation_repository_returns_none_for_unknown_id() -> None:
    repository: ProviderModelObservationRepository = InMemoryProviderModelObservationRepository()

    assert repository.get(FIRST_OBSERVATION_ID) is None


def test_memory_observation_repository_preserves_insertion_order() -> None:
    repository: ProviderModelObservationRepository = InMemoryProviderModelObservationRepository()

    first = create_first_observation()
    second = create_second_observation()
    other = create_other_observation()

    repository.save(first)

    repository.save(second)

    repository.save(other)

    assert repository.observations() == (
        first,
        second,
        other,
    )


def test_memory_observation_repository_filters_model_history() -> None:
    repository: ProviderModelObservationRepository = InMemoryProviderModelObservationRepository()

    first = create_first_observation()
    second = create_second_observation()
    other = create_other_observation()

    repository.save(first)

    repository.save(other)

    repository.save(second)

    assert repository.observations_for_model("example/frontier") == (
        first,
        second,
    )


def test_memory_observation_repository_returns_latest_model_observation() -> None:
    repository: ProviderModelObservationRepository = InMemoryProviderModelObservationRepository()

    first = create_first_observation()
    second = create_second_observation()

    repository.save(first)

    repository.save(second)

    assert repository.latest("example/frontier") == second


def test_memory_observation_repository_returns_none_without_model_history() -> None:
    repository: ProviderModelObservationRepository = InMemoryProviderModelObservationRepository()

    assert repository.latest("example/frontier") is None


def test_memory_observation_repository_rejects_duplicate_observation_id() -> None:
    repository = InMemoryProviderModelObservationRepository()

    observation = create_first_observation()

    repository.save(observation)

    with pytest.raises(
        ValueError,
        match=(f"Provider model observation {FIRST_OBSERVATION_ID} already exists"),
    ):
        repository.save(observation)


def test_memory_observation_repository_allows_equal_model_facts_as_distinct_evidence() -> None:
    repository = InMemoryProviderModelObservationRepository()

    first = create_first_observation()

    second = ProviderModelObservation(
        id=SECOND_OBSERVATION_ID,
        observed_at=SECOND_OBSERVED_AT,
        model=create_provider_model(),
    )

    assert first.fingerprint == second.fingerprint

    repository.save(first)

    repository.save(second)

    assert repository.observations_for_model("example/frontier") == (
        first,
        second,
    )

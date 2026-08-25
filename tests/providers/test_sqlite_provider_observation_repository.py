"""Tests for SQLite provider model observation persistence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.providers import (
    ModelPricing,
    ProviderModel,
    ProviderModelObservation,
    ProviderModelObservationRepository,
    SQLiteProviderModelObservationRepository,
)

FIRST_OBSERVATION_ID = UUID(
    "11111111-1111-1111-1111-111111111111"
)

SECOND_OBSERVATION_ID = UUID(
    "22222222-2222-2222-2222-222222222222"
)

OTHER_OBSERVATION_ID = UUID(
    "33333333-3333-3333-3333-333333333333"
)


def create_observation(
    *,
    observation_id: UUID,
    model: str = "frontier",
    hour: int,
    price: float = 1.0,
) -> ProviderModelObservation:
    """Create deterministic provider model evidence."""

    return ProviderModelObservation(
        id=observation_id,
        observed_at=datetime(
            2026,
            8,
            24,
            hour,
            0,
            0,
            tzinfo=UTC,
        ),
        model=ProviderModel(
            provider="example",
            model=model,
            display_name=model.title(),
            context_window_tokens=128_000,
            pricing=ModelPricing(
                input_usd_per_million_tokens=price,
                output_usd_per_million_tokens=price * 4,
            ),
        ),
    )


def create_repository(
    database: Path,
) -> SQLiteProviderModelObservationRepository:
    """Create one SQLite observation repository."""

    return SQLiteProviderModelObservationRepository(
        database
    )


def test_sqlite_observation_repository_satisfies_protocol(
    tmp_path: Path,
) -> None:
    repository: ProviderModelObservationRepository = (
        create_repository(
            tmp_path / "observations.db"
        )
    )

    assert repository.observations() == ()


def test_sqlite_observation_repository_persists_across_instances(
    tmp_path: Path,
) -> None:
    database = tmp_path / "observations.db"

    observation = create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        hour=20,
    )

    create_repository(
        database
    ).save(
        observation
    )

    repository = create_repository(
        database
    )

    assert repository.get(
        observation.id
    ) == observation


def test_sqlite_observation_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "observations.db"
    )

    first = create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        hour=20,
    )

    second = create_observation(
        observation_id=SECOND_OBSERVATION_ID,
        hour=21,
        price=0.5,
    )

    other = create_observation(
        observation_id=OTHER_OBSERVATION_ID,
        model="other",
        hour=22,
    )

    repository.save(
        first
    )

    repository.save(
        second
    )

    repository.save(
        other
    )

    assert repository.observations() == (
        first,
        second,
        other,
    )


def test_sqlite_observation_repository_returns_model_history(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "observations.db"
    )

    first = create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        hour=20,
    )

    other = create_observation(
        observation_id=OTHER_OBSERVATION_ID,
        model="other",
        hour=21,
    )

    second = create_observation(
        observation_id=SECOND_OBSERVATION_ID,
        hour=22,
        price=0.5,
    )

    repository.save(
        first
    )

    repository.save(
        other
    )

    repository.save(
        second
    )

    assert repository.observations_for_model(
        "example/frontier"
    ) == (
        first,
        second,
    )


def test_sqlite_observation_repository_returns_latest_model_observation(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "observations.db"
    )

    first = create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        hour=20,
    )

    second = create_observation(
        observation_id=SECOND_OBSERVATION_ID,
        hour=21,
        price=0.5,
    )

    repository.save(
        first
    )

    repository.save(
        second
    )

    assert repository.latest(
        "example/frontier"
    ) == second


def test_sqlite_observation_repository_returns_none_for_unknown_values(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "observations.db"
    )

    assert repository.get(
        FIRST_OBSERVATION_ID
    ) is None

    assert repository.latest(
        "example/frontier"
    ) is None

    assert repository.observations_for_model(
        "example/frontier"
    ) == ()


def test_sqlite_observation_repository_rejects_duplicate_observation_id(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "observations.db"
    )

    observation = create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        hour=20,
    )

    repository.save(
        observation
    )

    with pytest.raises(
        ValueError,
        match=(
            f"Provider model observation "
            f"{FIRST_OBSERVATION_ID} already exists"
        ),
    ):
        repository.save(
            observation
        )


def test_sqlite_observation_repository_allows_equal_fingerprints(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path / "observations.db"
    )

    first = create_observation(
        observation_id=FIRST_OBSERVATION_ID,
        hour=20,
    )

    second = create_observation(
        observation_id=SECOND_OBSERVATION_ID,
        hour=21,
    )

    assert first.fingerprint == second.fingerprint

    repository.save(
        first
    )

    repository.save(
        second
    )

    assert repository.observations_for_model(
        "example/frontier"
    ) == (
        first,
        second,
    )

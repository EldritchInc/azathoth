"""Tests for SQLite model metadata persistence."""

from pathlib import Path

import pytest

from azathoth.providers import (
    ModelCapability,
    ModelMetadata,
    ModelPricing,
    ModelRepository,
    SQLiteModelRepository,
    require_model_repository,
)

FIRST_IDENTIFIER = "openrouter/example/first-model"
SECOND_IDENTIFIER = "openrouter/example/second-model"
THIRD_IDENTIFIER = "other/example-model"


def create_first_model() -> ModelMetadata:
    """Create deterministic first model metadata."""

    return ModelMetadata(
        provider="openrouter",
        model="example/first-model",
        display_name="First Model",
        capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        context_window_tokens=32_768,
        maximum_output_tokens=8_192,
        pricing=ModelPricing(
            input_usd_per_million_tokens=0.1,
            output_usd_per_million_tokens=0.2,
        ),
    )


def create_second_model() -> ModelMetadata:
    """Create deterministic second model metadata."""

    return ModelMetadata(
        provider="openrouter",
        model="example/second-model",
        display_name="Second Model",
        context_window_tokens=8_192,
        pricing=ModelPricing(
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=2.0,
        ),
    )


def create_third_model() -> ModelMetadata:
    """Create deterministic metadata for another provider."""

    return ModelMetadata(
        provider="other",
        model="example-model",
        display_name="Other Model",
        context_window_tokens=16_384,
    )


def test_sqlite_model_repository_saves_and_gets_model(
    tmp_path: Path,
) -> None:
    repository = SQLiteModelRepository(tmp_path / "models.db")

    model = create_first_model()

    repository.save(model)

    restored = repository.get(FIRST_IDENTIFIER)

    assert restored == model
    assert restored is not model


def test_sqlite_model_repository_returns_none_for_unknown_model(
    tmp_path: Path,
) -> None:
    repository = SQLiteModelRepository(tmp_path / "models.db")

    assert repository.get(FIRST_IDENTIFIER) is None


def test_sqlite_model_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = SQLiteModelRepository(tmp_path / "models.db")

    first = create_first_model()
    second = create_second_model()
    third = create_third_model()

    repository.save(first)
    repository.save(second)
    repository.save(third)

    assert repository.models() == (
        first,
        second,
        third,
    )


def test_sqlite_model_repository_filters_by_provider(
    tmp_path: Path,
) -> None:
    repository = SQLiteModelRepository(tmp_path / "models.db")

    first = create_first_model()
    second = create_second_model()
    third = create_third_model()

    repository.save(first)
    repository.save(second)
    repository.save(third)

    assert repository.models_for_provider("openrouter") == (
        first,
        second,
    )

    assert repository.models_for_provider("other") == (third,)


def test_sqlite_model_repository_returns_empty_for_unknown_provider(
    tmp_path: Path,
) -> None:
    repository = SQLiteModelRepository(tmp_path / "models.db")

    repository.save(create_first_model())

    assert repository.models_for_provider("unknown") == ()


def test_sqlite_model_repository_rejects_duplicate_identifier(
    tmp_path: Path,
) -> None:
    repository = SQLiteModelRepository(tmp_path / "models.db")

    model = create_first_model()

    repository.save(model)

    with pytest.raises(
        ValueError,
        match=("Model 'openrouter/example/first-model' already exists"),
    ):
        repository.save(model)


def test_sqlite_model_repository_survives_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "models.db"

    model = create_first_model()

    SQLiteModelRepository(database).save(model)

    restored = SQLiteModelRepository(database).get(FIRST_IDENTIFIER)

    assert restored == model
    assert restored is not model


def test_sqlite_model_repository_preserves_complete_model_metadata(
    tmp_path: Path,
) -> None:
    database = tmp_path / "models.db"

    model = create_first_model()

    SQLiteModelRepository(database).save(model)

    restored = SQLiteModelRepository(database).get(FIRST_IDENTIFIER)

    assert restored is not None

    assert restored.provider == "openrouter"
    assert restored.model == "example/first-model"
    assert restored.display_name == "First Model"

    assert ModelCapability.STRUCTURED_OUTPUT in restored.capabilities

    assert restored.context_window_tokens == 32_768
    assert restored.maximum_output_tokens == 8_192

    assert restored.pricing is not None
    assert restored.pricing.input_usd_per_million_tokens == 0.1
    assert restored.pricing.output_usd_per_million_tokens == 0.2


def test_sqlite_model_repository_satisfies_protocol(
    tmp_path: Path,
) -> None:
    repository: ModelRepository = require_model_repository(
        SQLiteModelRepository(tmp_path / "models.db")
    )

    assert repository.models() == ()

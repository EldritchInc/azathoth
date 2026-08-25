"""Opt-in live verification of OpenRouter model discovery and observation."""

import asyncio
import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from azathoth.providers import (
    OpenRouterConfiguration,
    OpenRouterModelDirectory,
    ProviderModelObserver,
    SQLiteProviderModelObservationRepository,
)

RUN_LIVE_OPENROUTER_TESTS = os.environ.get("AZATHOTH_RUN_LIVE_OPENROUTER_TESTS") == "1"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

pytestmark = pytest.mark.skipif(
    not RUN_LIVE_OPENROUTER_TESTS or not OPENROUTER_API_KEY,
    reason=(
        "Live OpenRouter tests require AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1 and OPENROUTER_API_KEY."
    ),
)


def test_live_openrouter_model_observation_polling(
    tmp_path: Path,
) -> None:
    """Discover, persist, and deduplicate real OpenRouter model state."""

    assert OPENROUTER_API_KEY is not None

    directory = OpenRouterModelDirectory(
        OpenRouterConfiguration(api_key=SecretStr(OPENROUTER_API_KEY))
    )

    models = asyncio.run(directory.models())

    assert models

    discovered = models[0]

    database = tmp_path / "openrouter-model-observations.db"

    repository = SQLiteProviderModelObservationRepository(database)

    observer = ProviderModelObserver(
        directory=directory,
        repository=repository,
    )

    first = asyncio.run(observer.observe_model(discovered.model))

    assert first is not None
    assert first.created

    assert first.observation.provider == "openrouter"

    assert first.observation.model_identifier == discovered.model

    assert first.observation.identifier == discovered.identifier

    assert first.observation.fingerprint == discovered.fingerprint

    second = asyncio.run(observer.observe_model(discovered.model))

    assert second is not None
    assert not second.created

    assert second.observation.id == first.observation.id

    assert second.observation.fingerprint == first.observation.fingerprint

    assert repository.observations_for_model(discovered.identifier) == (first.observation,)

    reconstructed_repository = SQLiteProviderModelObservationRepository(database)

    assert reconstructed_repository.latest(discovered.identifier) == first.observation

"""Opt-in live verification of multiple OpenRouter model registrations."""

import asyncio
import os

import pytest
from pydantic import SecretStr

from azathoth.providers import (
    ModelCatalog,
    ModelMetadata,
    OpenRouterConfiguration,
    OpenRouterModelRegistryLoader,
    Prompt,
)

_LIVE_TEST_FLAG = "AZATHOTH_RUN_LIVE_OPENROUTER_TESTS"
_API_KEY_VARIABLE = "OPENROUTER_API_KEY"
_MODELS_VARIABLE = "OPENROUTER_TEST_MODELS"


def live_tests_enabled() -> bool:
    """Return whether live OpenRouter tests were explicitly enabled."""

    return os.getenv(_LIVE_TEST_FLAG) == "1"


def require_environment_variable(
    name: str,
) -> str:
    """Return one required non-empty environment variable."""

    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(f"Environment variable {name} is required.")

    return value.strip()


def require_test_models() -> tuple[str, ...]:
    """Return at least two configured OpenRouter test models."""

    raw_models = require_environment_variable(_MODELS_VARIABLE)

    models = tuple(model.strip() for model in raw_models.split(",") if model.strip())

    if len(models) < 2:
        raise RuntimeError(
            f"{_MODELS_VARIABLE} must contain at least two comma-separated OpenRouter models."
        )

    if len(models) != len(set(models)):
        raise RuntimeError(f"{_MODELS_VARIABLE} must contain unique model identifiers.")

    return models


def create_catalog(
    models: tuple[str, ...],
) -> ModelCatalog:
    """Create catalog metadata for live OpenRouter models."""

    return ModelCatalog(
        models=tuple(
            ModelMetadata(
                provider="openrouter",
                model=model,
                display_name=f"Live OpenRouter Test Model: {model}",
                context_window_tokens=8_192,
            )
            for model in models
        )
    )


@pytest.mark.skipif(
    not live_tests_enabled(),
    reason=("Live OpenRouter tests require AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1."),
)
def test_multiple_openrouter_models_execute_live_from_one_registry() -> None:
    api_key = require_environment_variable(_API_KEY_VARIABLE)

    models = require_test_models()

    catalog = create_catalog(models)

    registry = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(
            api_key=SecretStr(api_key),
        )
    ).load_registry(catalog)

    expected_identifiers = tuple(f"openrouter/{model}" for model in models)

    assert registry.identifiers == expected_identifiers

    async def complete_all_models() -> None:
        for model in models:
            identifier = f"openrouter/{model}"

            language_model = registry.get(identifier)

            assert language_model is not None

            response = await language_model.complete(
                Prompt(
                    text=("Reply with exactly the single word 'azathoth'."),
                )
            )

            assert response.provider == "openrouter"
            assert response.model == model

            assert response.resolved_model is not None
            assert response.resolved_model

            assert response.text.strip().lower() == "azathoth"

            assert response.prompt_tokens > 0
            assert response.completion_tokens > 0
            assert response.total_tokens > 0

            assert response.total_tokens == (response.prompt_tokens + response.completion_tokens)

            assert response.latency_ms >= 0
            assert response.estimated_cost_usd >= 0.0

    asyncio.run(complete_all_models())

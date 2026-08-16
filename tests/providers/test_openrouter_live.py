"""Opt-in live tests for the OpenRouter language model."""

import asyncio
import os

import pytest
from pydantic import SecretStr

from azathoth.providers import (
    OpenRouterConfiguration,
    OpenRouterLanguageModel,
    Prompt,
)

_LIVE_TEST_FLAG = "AZATHOTH_RUN_LIVE_OPENROUTER_TESTS"
_API_KEY_VARIABLE = "OPENROUTER_API_KEY"
_MODEL_VARIABLE = "OPENROUTER_TEST_MODEL"


def live_tests_enabled() -> bool:
    """Return whether live OpenRouter testing was explicitly requested."""

    return os.environ.get(_LIVE_TEST_FLAG) == "1"


def require_environment_variable(name: str) -> str:
    """Return a required environment variable for live testing."""

    value = os.environ.get(name)

    if not value:
        pytest.skip(f"{name} is required for live OpenRouter testing.")

    return value


@pytest.mark.skipif(
    not live_tests_enabled(),
    reason=("Live OpenRouter tests require AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1."),
)
def test_openrouter_language_model_completes_live_request() -> None:
    api_key = require_environment_variable(_API_KEY_VARIABLE)
    model_name = require_environment_variable(_MODEL_VARIABLE)

    language_model = OpenRouterLanguageModel(
        OpenRouterConfiguration(
            api_key=SecretStr(api_key),
        ),
        model_name,
    )

    response = asyncio.run(
        language_model.complete(
            Prompt(
                text="Return exactly the word success.",
            )
        )
    )

    assert response.text.strip()
    assert response.provider == "openrouter"
    assert response.model
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.total_tokens > 0
    assert response.latency_ms >= 0
    assert response.estimated_cost_usd >= 0.0

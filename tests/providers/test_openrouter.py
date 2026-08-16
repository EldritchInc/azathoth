"""Tests for the OpenRouter language model."""

import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from azathoth.providers import (
    ModelExecutionError,
    OpenRouterConfiguration,
    OpenRouterLanguageModel,
    Prompt,
)


def create_configuration() -> OpenRouterConfiguration:
    """Create deterministic OpenRouter configuration."""

    return OpenRouterConfiguration(
        api_key=SecretStr("test-openrouter-key"),
        base_url="https://openrouter.test/api/v1",
        timeout_seconds=10.0,
    )


def create_response() -> dict[str, Any]:
    """Create a deterministic OpenRouter response."""

    return {
        "id": "generation-1",
        "model": "openai/gpt-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "positive",
                },
            },
        ],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": 1,
            "total_tokens": 8,
            "cost": 0.000012,
        },
    }


def test_openrouter_language_model_returns_completion() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=create_response(),
            request=request,
        )

    model = OpenRouterLanguageModel(
        create_configuration(),
        "openai/gpt-test",
        transport=httpx.MockTransport(handler),
    )

    response = asyncio.run(
        model.complete(
            Prompt(
                text="Classify this text as positive or negative.",
            )
        )
    )

    assert response.text == "positive"
    assert response.provider == "openrouter"
    assert response.model == "openai/gpt-test"
    assert response.resolved_model == "openai/gpt-test"


def test_openrouter_language_model_records_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=create_response(),
            request=request,
        )

    model = OpenRouterLanguageModel(
        create_configuration(),
        "openai/gpt-test",
        transport=httpx.MockTransport(handler),
    )

    response = asyncio.run(
        model.complete(
            Prompt(
                text="Classify this text as positive or negative.",
            )
        )
    )

    assert response.prompt_tokens == 7
    assert response.completion_tokens == 1
    assert response.total_tokens == 8
    assert response.estimated_cost_usd == 0.000012
    assert response.latency_ms >= 0


def test_openrouter_language_model_sends_expected_request() -> None:
    recorded_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal recorded_request

        recorded_request = request

        return httpx.Response(
            200,
            json=create_response(),
            request=request,
        )

    model = OpenRouterLanguageModel(
        create_configuration(),
        "openai/gpt-test",
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(
        model.complete(
            Prompt(
                text="Classify this text.",
            )
        )
    )

    assert recorded_request is not None
    assert recorded_request.url == ("https://openrouter.test/api/v1/chat/completions")
    assert recorded_request.headers["Authorization"] == "Bearer test-openrouter-key"

    body = json.loads(recorded_request.content)

    assert body == {
        "model": "openai/gpt-test",
        "messages": [
            {
                "role": "user",
                "content": "Classify this text.",
            },
        ],
    }


def test_openrouter_language_model_rejects_empty_model() -> None:
    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        OpenRouterLanguageModel(
            create_configuration(),
            "",
        )


def test_openrouter_language_model_maps_http_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": "Unauthorized",
                },
            },
            request=request,
        )

    model = OpenRouterLanguageModel(
        create_configuration(),
        "openai/gpt-test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(
        ModelExecutionError,
        match="OpenRouter request",
    ):
        asyncio.run(
            model.complete(
                Prompt(
                    text="Hello.",
                )
            )
        )


def test_openrouter_language_model_maps_invalid_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "invalid": True,
            },
            request=request,
        )

    model = OpenRouterLanguageModel(
        create_configuration(),
        "openai/gpt-test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(
        ModelExecutionError,
        match="invalid response",
    ):
        asyncio.run(
            model.complete(
                Prompt(
                    text="Hello.",
                )
            )
        )


def test_openrouter_language_model_preserves_resolved_model() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = create_response()
        payload["model"] = "deepseek/deepseek-v4-flash-0731"

        return httpx.Response(
            200,
            json=payload,
            request=request,
        )

    model = OpenRouterLanguageModel(
        create_configuration(),
        "~deepseek/deepseek-v4-flash-latest",
        transport=httpx.MockTransport(handler),
    )

    response = asyncio.run(
        model.complete(
            Prompt(
                text="Return exactly positive.",
            )
        )
    )

    assert response.model == "~deepseek/deepseek-v4-flash-latest"
    assert response.resolved_model == "deepseek/deepseek-v4-flash-0731"

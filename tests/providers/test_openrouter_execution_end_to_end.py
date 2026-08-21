"""End-to-end tests for OpenRouter model execution."""

import asyncio
from typing import Any

import httpx
from pydantic import SecretStr

from azathoth.providers import (
    ModelExecutor,
    ModelRequest,
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
    """Create deterministic OpenRouter response."""

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


def create_language_model() -> OpenRouterLanguageModel:
    """Create deterministic OpenRouter language model."""

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=create_response(),
            request=request,
        )

    return OpenRouterLanguageModel(
        create_configuration(),
        "openai/gpt-test",
        transport=httpx.MockTransport(handler),
    )


def create_request() -> ModelRequest:
    """Create deterministic model request."""

    return ModelRequest(
        prompt=Prompt(
            text="Classify this text as positive or negative.",
        ),
    )


def test_model_request_executes_end_to_end() -> None:
    executor = ModelExecutor()

    response = asyncio.run(
        executor.execute(
            create_request(),
            create_language_model(),
        )
    )

    assert response.text == "positive"
    assert response.provider == "openrouter"
    assert response.model == "openai/gpt-test"
    assert response.prompt_tokens == 7
    assert response.completion_tokens == 1
    assert response.total_tokens == 8
    assert response.latency_ms >= 0
    assert response.estimated_cost_usd == 0.000012


def test_model_request_round_trips_before_execution() -> None:
    request = create_request()

    restored = ModelRequest.model_validate_json(
        request.model_dump_json(),
    )

    response = asyncio.run(
        ModelExecutor().execute(
            restored,
            create_language_model(),
        )
    )

    assert restored == request
    assert response.text == "positive"


def test_model_response_round_trips_after_execution() -> None:
    response = asyncio.run(
        ModelExecutor().execute(
            create_request(),
            create_language_model(),
        )
    )

    restored = response.model_validate_json(
        response.model_dump_json(),
    )

    assert restored == response


def test_execution_is_deterministic() -> None:
    executor = ModelExecutor()

    first = asyncio.run(
        executor.execute(
            create_request(),
            create_language_model(),
        )
    )

    second = asyncio.run(
        executor.execute(
            create_request(),
            create_language_model(),
        )
    )

    assert first.text == second.text
    assert first.provider == second.provider
    assert first.model == second.model
    assert first.resolved_model == second.resolved_model

    assert first.prompt_tokens == second.prompt_tokens
    assert first.completion_tokens == second.completion_tokens
    assert first.total_tokens == second.total_tokens

    assert first.estimated_cost_usd == second.estimated_cost_usd

    assert first.latency_ms >= 0
    assert second.latency_ms >= 0


def test_complete_execution_lifecycle() -> None:
    request = create_request()

    restored_request = ModelRequest.model_validate_json(
        request.model_dump_json(),
    )

    response = asyncio.run(
        ModelExecutor().execute(
            restored_request,
            create_language_model(),
        )
    )

    restored_response = response.model_validate_json(
        response.model_dump_json(),
    )

    assert restored_request == request
    assert restored_response == response

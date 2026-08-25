"""Tests for OpenRouter provider model discovery."""

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from azathoth.providers import (
    ModelCapability,
    ModelDiscoveryError,
    ModelModality,
    OpenRouterConfiguration,
    OpenRouterModelDirectory,
    ProviderModelDirectory,
)


def create_configuration() -> OpenRouterConfiguration:
    """Create deterministic OpenRouter configuration."""

    return OpenRouterConfiguration(
        api_key=SecretStr("test-key"),
        base_url="https://openrouter.test/api/v1",
    )


def create_model_payload(
    *,
    model: str = "example/frontier",
) -> dict[
    str,
    object,
]:
    """Create deterministic OpenRouter model metadata."""

    return {
        "id": model,
        "canonical_slug": model,
        "name": "Frontier Model",
        "context_length": 128_000,
        "architecture": {
            "input_modalities": [
                "text",
                "image",
                "file",
            ],
            "output_modalities": [
                "text",
            ],
        },
        "pricing": {
            "prompt": "0.000001",
            "completion": "0.000004",
            "image": "0",
            "request": "0",
        },
        "supported_parameters": [
            "temperature",
            "tools",
            "structured_outputs",
        ],
        "top_provider": {
            "max_completion_tokens": 16_384,
        },
    }


def test_openrouter_directory_satisfies_provider_protocol() -> None:
    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [],
            },
        )

    directory: ProviderModelDirectory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    assert directory.provider == "openrouter"


def test_openrouter_directory_lists_normalized_models() -> None:
    requests: list[httpx.Request] = []

    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        requests.append(request)

        return httpx.Response(
            200,
            json={
                "data": [
                    create_model_payload(),
                ],
            },
        )

    directory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    models = asyncio.run(directory.models())

    assert len(models) == 1

    model = models[0]

    assert model.provider == "openrouter"
    assert model.model == "example/frontier"
    assert model.display_name == "Frontier Model"

    assert model.input_modalities == frozenset(
        {
            ModelModality.TEXT,
            ModelModality.IMAGE,
            ModelModality.FILE,
        }
    )

    assert model.output_modalities == frozenset(
        {
            ModelModality.TEXT,
        }
    )

    assert model.capabilities == frozenset(
        {
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.TOOL_USE,
            ModelCapability.VISION,
        }
    )

    assert model.context_window_tokens == 128_000
    assert model.maximum_output_tokens == 16_384

    assert model.pricing is not None

    assert model.pricing.input_usd_per_million_tokens == 1.0

    assert model.pricing.output_usd_per_million_tokens == 4.0

    assert len(requests) == 1

    request = requests[0]

    assert request.url.path == "/api/v1/models"

    assert request.url.params["output_modalities"] == "all"

    assert request.headers["Authorization"] == "Bearer test-key"


def test_openrouter_directory_resolves_one_model() -> None:
    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.url.path == "/api/v1/model/example/frontier"

        return httpx.Response(
            200,
            json={
                "data": create_model_payload(),
            },
        )

    directory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    model = asyncio.run(directory.model("example/frontier"))

    assert model is not None
    assert model.model == "example/frontier"


def test_openrouter_directory_returns_none_for_unknown_model() -> None:
    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(404)

    directory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    model = asyncio.run(directory.model("example/missing"))

    assert model is None


def test_openrouter_directory_preserves_alias_identifier() -> None:
    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = create_model_payload(model="anthropic/claude-sonnet-latest")

        payload["canonical_slug"] = "anthropic/claude-sonnet-4.6"

        return httpx.Response(
            200,
            json={
                "data": payload,
            },
        )

    directory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    model = asyncio.run(directory.model("anthropic/claude-sonnet-latest"))

    assert model is not None

    assert model.model == "anthropic/claude-sonnet-latest"


def test_openrouter_directory_supports_non_text_modalities() -> None:
    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = create_model_payload()

        architecture = payload["architecture"]

        assert isinstance(
            architecture,
            dict,
        )

        architecture["output_modalities"] = [
            "image",
            "audio",
            "embeddings",
        ]

        return httpx.Response(
            200,
            json={
                "data": [
                    payload,
                ],
            },
        )

    directory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    models = asyncio.run(directory.models())

    assert models[0].output_modalities == frozenset(
        {
            ModelModality.IMAGE,
            ModelModality.AUDIO,
            ModelModality.EMBEDDINGS,
        }
    )


def test_openrouter_directory_ignores_unknown_modalities() -> None:
    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = create_model_payload()

        architecture = payload["architecture"]

        assert isinstance(
            architecture,
            dict,
        )

        architecture["input_modalities"] = [
            "text",
            "telepathy",
        ]

        return httpx.Response(
            200,
            json={
                "data": [
                    payload,
                ],
            },
        )

    directory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    models = asyncio.run(directory.models())

    assert models[0].input_modalities == frozenset(
        {
            ModelModality.TEXT,
        }
    )


def test_openrouter_directory_omits_unknown_pricing() -> None:
    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = create_model_payload()

        payload["pricing"] = {
            "prompt": "-1",
            "completion": "-1",
        }

        return httpx.Response(
            200,
            json={
                "data": [
                    payload,
                ],
            },
        )

    directory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    models = asyncio.run(directory.models())

    assert models[0].pricing is None


def test_openrouter_directory_raises_discovery_error_for_http_failure() -> None:
    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(500)

    directory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    with pytest.raises(
        ModelDiscoveryError,
        match="OpenRouter model discovery request failed",
    ):
        asyncio.run(directory.models())


def test_openrouter_directory_raises_discovery_error_for_invalid_payload() -> None:
    async def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "definitely": "not a model",
                    },
                ],
            },
        )

    directory = OpenRouterModelDirectory(
        create_configuration(),
        transport=httpx.MockTransport(handle_request),
    )

    with pytest.raises(
        ModelDiscoveryError,
        match=("OpenRouter returned invalid model directory data"),
    ):
        asyncio.run(directory.models())


def test_openrouter_directory_rejects_empty_model_identifier() -> None:
    directory = OpenRouterModelDirectory(create_configuration())

    with pytest.raises(
        ValueError,
        match=("OpenRouter model identifier must not be empty"),
    ):
        asyncio.run(directory.model(""))

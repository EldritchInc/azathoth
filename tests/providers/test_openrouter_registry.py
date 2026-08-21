"""Tests for OpenRouter model registry assembly."""

import httpx
from pydantic import SecretStr

from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    OpenRouterConfiguration,
    OpenRouterModelRegistryLoader,
)

FIRST_MODEL = "example/first-model"
SECOND_MODEL = "example/second-model"
THIRD_MODEL = "example/third-model"

FIRST_IDENTIFIER = f"openrouter/{FIRST_MODEL}"
SECOND_IDENTIFIER = f"openrouter/{SECOND_MODEL}"
THIRD_IDENTIFIER = f"openrouter/{THIRD_MODEL}"


def create_configuration() -> OpenRouterConfiguration:
    """Create deterministic OpenRouter configuration."""

    return OpenRouterConfiguration(
        api_key=SecretStr("test-key"),
    )


def create_catalog() -> ModelCatalog:
    """Create a catalog containing multiple OpenRouter models."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="openrouter",
                model=FIRST_MODEL,
                display_name="First Model",
                context_window_tokens=8_192,
            ),
            ModelMetadata(
                provider="openrouter",
                model=SECOND_MODEL,
                display_name="Second Model",
                context_window_tokens=16_384,
            ),
            ModelMetadata(
                provider="openrouter",
                model=THIRD_MODEL,
                display_name="Third Model",
                context_window_tokens=32_768,
            ),
        ),
    )


def test_openrouter_registry_loader_builds_all_configured_models() -> None:
    registry = OpenRouterModelRegistryLoader(create_configuration()).load_registry(create_catalog())

    assert registry.get(FIRST_IDENTIFIER) is not None

    assert registry.get(SECOND_IDENTIFIER) is not None

    assert registry.get(THIRD_IDENTIFIER) is not None


def test_openrouter_registry_loader_ignores_other_providers() -> None:
    catalog = ModelCatalog(
        models=(
            ModelMetadata(
                provider="openrouter",
                model=FIRST_MODEL,
                display_name="First Model",
                context_window_tokens=8_192,
            ),
            ModelMetadata(
                provider="other-provider",
                model="other-model",
                display_name="Other Model",
                context_window_tokens=8_192,
            ),
        ),
    )

    registry = OpenRouterModelRegistryLoader(create_configuration()).load_registry(catalog)

    assert registry.get(FIRST_IDENTIFIER) is not None

    assert registry.get("other-provider/other-model") is None


def test_openrouter_registry_loader_returns_empty_registry_without_models() -> None:
    registry = OpenRouterModelRegistryLoader(create_configuration()).load_registry(ModelCatalog())

    assert registry.get(FIRST_IDENTIFIER) is None


def test_openrouter_registry_loader_returns_language_model_registry() -> None:
    registry = OpenRouterModelRegistryLoader(create_configuration()).load_registry(create_catalog())

    assert isinstance(
        registry,
        LanguageModelRegistry,
    )


def test_openrouter_registry_models_execute_independently() -> None:
    requested_models: list[str] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = request.content.decode()

        for model in (
            FIRST_MODEL,
            SECOND_MODEL,
            THIRD_MODEL,
        ):
            if f'"model":"{model}"' in payload:
                requested_models.append(model)

                return httpx.Response(
                    200,
                    json={
                        "model": model,
                        "choices": [
                            {
                                "message": {
                                    "content": (f"response from {model}"),
                                },
                            },
                        ],
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                            "cost": 0.0,
                        },
                    },
                )

        raise AssertionError("Unexpected OpenRouter model request.")

    transport = httpx.MockTransport(handler)

    registry = OpenRouterModelRegistryLoader(
        create_configuration(),
        transport=transport,
    ).load_registry(create_catalog())

    assert registry.get(FIRST_IDENTIFIER) is not None

    assert registry.get(SECOND_IDENTIFIER) is not None

    assert registry.get(THIRD_IDENTIFIER) is not None


def test_openrouter_registry_composes_with_existing_provider_registry() -> None:
    existing_model = DeterministicLanguageModel(
        provider="deterministic",
        model="existing-model",
    )

    existing_registry = LanguageModelRegistry(
        models={
            "deterministic/existing-model": existing_model,
        },
    )

    openrouter_registry = OpenRouterModelRegistryLoader(create_configuration()).load_registry(
        create_catalog()
    )

    combined = LanguageModelRegistry.compose(
        (
            existing_registry,
            openrouter_registry,
        )
    )

    assert combined.identifiers == (
        "deterministic/existing-model",
        FIRST_IDENTIFIER,
        SECOND_IDENTIFIER,
        THIRD_IDENTIFIER,
    )

    assert combined.get("deterministic/existing-model") is existing_model

    assert combined.get(FIRST_IDENTIFIER) is not None

    assert combined.get(SECOND_IDENTIFIER) is not None

    assert combined.get(THIRD_IDENTIFIER) is not None

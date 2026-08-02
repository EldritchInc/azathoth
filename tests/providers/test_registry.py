"""Tests for language model registry."""

import pytest

from azathoth.providers import (
    LanguageModelRegistry,
    ModelResponse,
    Prompt,
)


class StubLanguageModel:
    """A deterministic executable model for registry tests."""

    async def complete(self, prompt: Prompt) -> ModelResponse:
        return ModelResponse(
            text="response",
            provider="test-provider",
            model="test-model",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            latency_ms=1,
            estimated_cost_usd=0.0,
        )


def test_registry_resolves_language_model_by_identifier() -> None:
    model = StubLanguageModel()
    registry = LanguageModelRegistry(
        models={
            "test-provider/test-model": model,
        }
    )

    assert registry.get("test-provider/test-model") is model


def test_registry_returns_none_for_unknown_identifier() -> None:
    registry = LanguageModelRegistry()

    assert registry.get("missing/model") is None


def test_registry_preserves_identifier_order() -> None:
    registry = LanguageModelRegistry(
        models={
            "provider-a/model-a": StubLanguageModel(),
            "provider-b/model-b": StubLanguageModel(),
        }
    )

    assert registry.identifiers == (
        "provider-a/model-a",
        "provider-b/model-b",
    )


def test_registry_rejects_empty_identifier() -> None:
    with pytest.raises(
        ValueError,
        match="identifiers cannot be empty",
    ):
        LanguageModelRegistry(
            models={
                "": StubLanguageModel(),
            }
        )

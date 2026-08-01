"""Tests for language model protocol compatibility."""

import asyncio

from azathoth.providers import (
    LanguageModel,
    ModelResponse,
    Prompt,
)


class RecordingLanguageModel:
    """A test language model that records prompts."""

    def __init__(self) -> None:
        self.prompt: Prompt | None = None

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        self.prompt = prompt

        return ModelResponse(
            text="response",
            provider="test",
            model="stub",
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
            latency_ms=15,
            estimated_cost_usd=0.0001,
        )


def test_language_model_protocol() -> None:
    model: LanguageModel = RecordingLanguageModel()

    prompt = Prompt(
        text="Hello",
    )

    response = asyncio.run(model.complete(prompt))

    assert response.text == "response"
    assert response.provider == "test"
    assert response.model == "stub"
    assert response.total_tokens == 12
    assert response.latency_ms == 15
    assert response.estimated_cost_usd == 0.0001

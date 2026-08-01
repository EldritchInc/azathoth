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
        )


def test_language_model_protocol() -> None:
    model: LanguageModel = RecordingLanguageModel()

    prompt = Prompt(
        text="Hello",
    )

    response = asyncio.run(model.complete(prompt))

    assert response.text == "response"

"""Tests for provider-neutral model request execution."""

import asyncio

import pytest

from azathoth.providers import (
    ModelExecutor,
    ModelRequest,
    ModelResponse,
    Prompt,
    UnsupportedModelRequestError,
)


class RecordingLanguageModel:
    """Record prompts received through model request execution."""

    def __init__(self) -> None:
        self.received_prompt: Prompt | None = None

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record the prompt and return deterministic response evidence."""

        self.received_prompt = prompt

        return ModelResponse(
            text="classified",
            provider="test-provider",
            model="test-model",
            prompt_tokens=3,
            completion_tokens=1,
            total_tokens=4,
            latency_ms=5,
            estimated_cost_usd=0.001,
        )


def test_model_executor_executes_request_prompt() -> None:
    executor = ModelExecutor()
    language_model = RecordingLanguageModel()
    prompt = Prompt(
        text="Classify this request.",
    )

    response = asyncio.run(
        executor.execute(
            ModelRequest(
                prompt=prompt,
            ),
            language_model,
        )
    )

    assert language_model.received_prompt == prompt
    assert response.text == "classified"


def test_model_executor_returns_provider_response() -> None:
    executor = ModelExecutor()

    response = asyncio.run(
        executor.execute(
            ModelRequest(
                prompt=Prompt(
                    text="Classify this request.",
                ),
            ),
            RecordingLanguageModel(),
        )
    )

    assert response == ModelResponse(
        text="classified",
        provider="test-provider",
        model="test-model",
        prompt_tokens=3,
        completion_tokens=1,
        total_tokens=4,
        latency_ms=5,
        estimated_cost_usd=0.001,
    )


def test_model_executor_rejects_temperature_until_supported() -> None:
    executor = ModelExecutor()

    with pytest.raises(
        UnsupportedModelRequestError,
        match="temperature",
    ):
        asyncio.run(
            executor.execute(
                ModelRequest(
                    prompt=Prompt(
                        text="Classify this request.",
                    ),
                    temperature=0.0,
                ),
                RecordingLanguageModel(),
            )
        )


def test_model_executor_rejects_max_output_tokens_until_supported() -> None:
    executor = ModelExecutor()

    with pytest.raises(
        UnsupportedModelRequestError,
        match="max_output_tokens",
    ):
        asyncio.run(
            executor.execute(
                ModelRequest(
                    prompt=Prompt(
                        text="Classify this request.",
                    ),
                    max_output_tokens=25,
                ),
                RecordingLanguageModel(),
            )
        )


def test_model_executor_reports_all_unsupported_controls() -> None:
    executor = ModelExecutor()

    with pytest.raises(
        UnsupportedModelRequestError,
        match="temperature, max_output_tokens",
    ):
        asyncio.run(
            executor.execute(
                ModelRequest(
                    prompt=Prompt(
                        text="Classify this request.",
                    ),
                    temperature=0.0,
                    max_output_tokens=25,
                ),
                RecordingLanguageModel(),
            )
        )


def test_model_executor_does_not_call_model_for_unsupported_request() -> None:
    executor = ModelExecutor()
    language_model = RecordingLanguageModel()

    with pytest.raises(UnsupportedModelRequestError):
        asyncio.run(
            executor.execute(
                ModelRequest(
                    prompt=Prompt(
                        text="Classify this request.",
                    ),
                    temperature=0.5,
                ),
                language_model,
            )
        )

    assert language_model.received_prompt is None

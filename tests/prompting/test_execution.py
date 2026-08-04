"""Tests for shared prompt execution behavior."""

import asyncio

import pytest

from azathoth.prompting import (
    ModelBinding,
    ModelBindingMismatchError,
)
from azathoth.prompting.execution import execute_prompt
from azathoth.providers import ModelResponse, Prompt


class RecordingLanguageModel:
    """A deterministic model that records the received prompt."""

    def __init__(
        self,
        *,
        provider: str = "provider-a",
        model: str = "small",
        response_text: str = "duplicate_charge",
    ) -> None:
        self._provider = provider
        self._model = model
        self._response_text = response_text
        self.received_prompt: Prompt | None = None

    async def complete(self, prompt: Prompt) -> ModelResponse:
        """Record the prompt and return deterministic execution evidence."""

        self.received_prompt = prompt

        return ModelResponse(
            text=self._response_text,
            provider=self._provider,
            model=self._model,
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
            latency_ms=15,
            estimated_cost_usd=0.0001,
        )


def test_execute_prompt_calls_language_model() -> None:
    prompt = Prompt(
        text="Classify this request.",
    )
    language_model = RecordingLanguageModel()

    outcome = asyncio.run(
        execute_prompt(
            prompt=prompt,
            language_model=language_model,
            model_binding=None,
        )
    )

    assert language_model.received_prompt == prompt
    assert outcome.output == "duplicate_charge"


def test_execute_prompt_translates_response_metrics() -> None:
    outcome = asyncio.run(
        execute_prompt(
            prompt=Prompt(
                text="Classify this request.",
            ),
            language_model=RecordingLanguageModel(),
            model_binding=None,
        )
    )

    assert outcome.metrics is not None
    assert outcome.metrics.provider == "provider-a"
    assert outcome.metrics.model == "small"
    assert outcome.metrics.prompt_tokens == 10
    assert outcome.metrics.completion_tokens == 2
    assert outcome.metrics.total_tokens == 12
    assert outcome.metrics.latency_ms == 15
    assert outcome.metrics.estimated_cost_usd == 0.0001


def test_execute_prompt_accepts_matching_model_binding() -> None:
    outcome = asyncio.run(
        execute_prompt(
            prompt=Prompt(
                text="Classify this request.",
            ),
            language_model=RecordingLanguageModel(),
            model_binding=ModelBinding(
                identifier="provider-a/small",
            ),
        )
    )

    assert outcome.output == "duplicate_charge"


def test_execute_prompt_rejects_mismatched_model_binding() -> None:
    with pytest.raises(
        ModelBindingMismatchError,
        match="provider-b/large",
    ):
        asyncio.run(
            execute_prompt(
                prompt=Prompt(
                    text="Classify this request.",
                ),
                language_model=RecordingLanguageModel(
                    provider="provider-b",
                    model="large",
                ),
                model_binding=ModelBinding(
                    identifier="provider-a/small",
                ),
            )
        )

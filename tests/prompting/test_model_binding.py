"""Tests for prompt strategy model bindings."""

import asyncio

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.prompting import ModelBinding, PromptStrategy
from azathoth.providers import ModelResponse, Prompt
from azathoth.strategies import StrategyMetadata


class RecordingLanguageModel:
    """A deterministic language model for binding tests."""

    def __init__(self) -> None:
        self.received_prompt: Prompt | None = None

    async def complete(self, prompt: Prompt) -> ModelResponse:
        """Record the prompt and return a deterministic response."""

        self.received_prompt = prompt

        return ModelResponse(
            text="duplicate_charge",
            provider="provider-a",
            model="model-small",
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
            latency_ms=15,
            estimated_cost_usd=0.0001,
        )


def create_strategy(
    *,
    language_model: RecordingLanguageModel,
    model_binding: ModelBinding | None = None,
) -> PromptStrategy:
    """Create a deterministic prompt strategy."""

    return PromptStrategy(
        metadata=StrategyMetadata(
            name="Classify support request",
            description="Classify a support request using a language model.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text="Classify the support request.",
        ),
        language_model=language_model,
        model_binding=model_binding,
    )


def test_model_binding_records_provider_qualified_identifier() -> None:
    binding = ModelBinding(
        identifier="provider-a/model-small",
    )

    assert binding.identifier == "provider-a/model-small"


def test_model_binding_rejects_empty_identifier() -> None:
    with pytest.raises(ValidationError):
        ModelBinding(identifier="")


def test_model_binding_is_immutable() -> None:
    binding = ModelBinding(
        identifier="provider-a/model-small",
    )

    with pytest.raises(ValidationError):
        binding.identifier = "provider-b/model-large"


def test_model_binding_round_trips_through_json() -> None:
    binding = ModelBinding(
        identifier="provider-a/model-small",
    )

    restored = ModelBinding.model_validate_json(binding.model_dump_json())

    assert restored == binding


def test_prompt_strategy_exposes_model_binding() -> None:
    binding = ModelBinding(
        identifier="provider-a/model-small",
    )

    strategy = create_strategy(
        language_model=RecordingLanguageModel(),
        model_binding=binding,
    )

    assert strategy.model_binding == binding


def test_prompt_strategy_allows_omitted_model_binding() -> None:
    strategy = create_strategy(
        language_model=RecordingLanguageModel(),
    )

    assert strategy.model_binding is None


def test_model_binding_does_not_change_execution() -> None:
    model = RecordingLanguageModel()
    binding = ModelBinding(
        identifier="provider-a/model-small",
    )
    strategy = create_strategy(
        language_model=model,
        model_binding=binding,
    )

    outcome = asyncio.run(strategy.run(Context()))

    assert model.received_prompt == Prompt(
        text="Classify the support request.",
    )
    assert outcome.output == "duplicate_charge"

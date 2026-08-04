"""Tests for language-model-backed prompt strategies."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.prompting import ModelBinding, ModelBindingMismatchError, PromptStrategy
from azathoth.providers import ModelCapability, ModelRequirements, ModelResponse, Prompt
from azathoth.strategies import Strategy, StrategyMetadata


class RecordingLanguageModel:
    """A deterministic test model that records the received prompt."""

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.received_prompt: Prompt | None = None

    async def complete(self, prompt: Prompt) -> ModelResponse:
        """Record the prompt and return a configured response."""

        self.received_prompt = prompt

        return ModelResponse(
            text=self._response_text,
            provider="test",
            model="stub",
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
            latency_ms=15,
            estimated_cost_usd=0.0001,
        )


class MismatchedLanguageModel:
    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        return ModelResponse(
            text="wrong",
            provider="provider-b",
            model="large",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            latency_ms=1,
            estimated_cost_usd=0,
        )


async def execute_strategy(
    strategy: Strategy,
    context: Context,
) -> str:
    """Execute a strategy through the common strategy protocol."""

    outcome = await strategy.run(context)

    assert isinstance(outcome.output, str)

    return outcome.output


def create_metadata() -> StrategyMetadata:
    """Create deterministic strategy metadata."""

    return StrategyMetadata(
        id=UUID("8427950d-926e-4251-a6c7-015d6afcfa3d"),
        name="Classify support request",
        description="Classify a support request using a language model.",
        version="1.0.0",
    )


def test_prompt_strategy_sends_prompt_to_language_model() -> None:
    model = RecordingLanguageModel(
        response_text="duplicate_charge",
    )
    prompt = Prompt(
        text="Classify this support request.",
    )
    strategy = PromptStrategy(
        metadata=create_metadata(),
        prompt=prompt,
        language_model=model,
    )

    outcome = asyncio.run(strategy.run(Context()))

    assert model.received_prompt == prompt
    assert outcome.output == "duplicate_charge"


def test_prompt_strategy_returns_model_response_as_strategy_output() -> None:
    model = RecordingLanguageModel(
        response_text="refund_request",
    )
    strategy = PromptStrategy(
        metadata=create_metadata(),
        prompt=Prompt(
            text="Return the support category.",
        ),
        language_model=model,
    )

    outcome = asyncio.run(strategy.run(Context()))

    assert outcome.output == "refund_request"
    assert outcome.events == ()
    assert outcome.metrics is not None
    assert outcome.metrics.provider == "test"
    assert outcome.metrics.model == "stub"
    assert outcome.metrics.prompt_tokens == 10
    assert outcome.metrics.completion_tokens == 2
    assert outcome.metrics.total_tokens == 12
    assert outcome.metrics.latency_ms == 15
    assert outcome.metrics.estimated_cost_usd == 0.0001


def test_prompt_strategy_exposes_metadata_and_prompt() -> None:
    metadata = create_metadata()
    prompt = Prompt(
        text="Classify the request.",
    )
    strategy = PromptStrategy(
        metadata=metadata,
        prompt=prompt,
        language_model=RecordingLanguageModel(
            response_text="account_access",
        ),
    )

    assert strategy.metadata == metadata
    assert strategy.prompt == prompt


def test_prompt_strategy_satisfies_strategy_protocol() -> None:
    strategy = PromptStrategy(
        metadata=create_metadata(),
        prompt=Prompt(
            text="Classify the request.",
        ),
        language_model=RecordingLanguageModel(
            response_text="duplicate_charge",
        ),
    )

    output = asyncio.run(
        execute_strategy(
            strategy=strategy,
            context=Context(),
        )
    )

    assert output == "duplicate_charge"


def test_prompt_strategy_exposes_model_requirements() -> None:
    requirements = ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        minimum_context_window_tokens=32_000,
    )

    strategy = PromptStrategy(
        metadata=create_metadata(),
        prompt=Prompt(
            text="Return structured JSON.",
        ),
        language_model=RecordingLanguageModel(
            response_text='{"category":"duplicate_charge"}',
        ),
        model_requirements=requirements,
    )

    assert strategy.model_requirements == requirements


def test_prompt_strategy_allows_omitted_model_requirements() -> None:
    strategy = PromptStrategy(
        metadata=create_metadata(),
        prompt=Prompt(
            text="Classify the request.",
        ),
        language_model=RecordingLanguageModel(
            response_text="duplicate_charge",
        ),
    )

    assert strategy.model_requirements is None


def test_model_requirements_do_not_change_prompt_execution() -> None:
    model = RecordingLanguageModel(
        response_text="duplicate_charge",
    )
    requirements = ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
    )
    prompt = Prompt(
        text="Classify the request.",
    )

    strategy = PromptStrategy(
        metadata=create_metadata(),
        prompt=prompt,
        language_model=model,
        model_requirements=requirements,
    )

    outcome = asyncio.run(strategy.run(Context()))

    assert model.received_prompt == prompt
    assert outcome.output == "duplicate_charge"


def test_prompt_strategy_rejects_mismatched_model_binding() -> None:
    strategy = PromptStrategy(
        metadata=create_metadata(),
        prompt=Prompt(text="Hello"),
        language_model=MismatchedLanguageModel(),
        model_binding=ModelBinding(
            identifier="provider-a/small",
        ),
    )

    with pytest.raises(ModelBindingMismatchError):
        asyncio.run(strategy.run(Context()))

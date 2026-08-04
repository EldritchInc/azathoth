"""Tests for context-aware prompt strategies."""

import asyncio

import pytest

from azathoth.context import Context, ContextEvent
from azathoth.prompting import (
    ContextPromptStrategy,
    ModelBinding,
    ModelBindingMismatchError,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import ModelCapability, ModelRequirements, ModelResponse, Prompt
from azathoth.strategies import Strategy, StrategyMetadata


class RecordingLanguageModel:
    """A deterministic model that records its rendered prompt."""

    def __init__(
        self,
        *,
        provider: str = "test-provider",
        model: str = "test-model",
        response_text: str,
    ) -> None:
        self._provider = provider
        self._model = model
        self._response_text = response_text
        self.received_prompt: Prompt | None = None

    async def complete(self, prompt: Prompt) -> ModelResponse:
        """Record the prompt and return a configured response."""

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


def create_strategy(
    *,
    language_model: RecordingLanguageModel,
    model_binding: ModelBinding | None = None,
) -> ContextPromptStrategy:
    """Create a deterministic context-aware prompt strategy."""

    return ContextPromptStrategy(
        metadata=StrategyMetadata(
            name="Classify support message",
            description="Classify a support message rendered from context.",
            version="1.0.0",
        ),
        template=PromptTemplate(
            text="Classify: {message}",
            bindings=(
                PromptBinding(
                    variable_name="message",
                    event_type="customer.message.received",
                    field_name="message",
                ),
            ),
        ),
        language_model=language_model,
        model_binding=model_binding,
    )


def create_context() -> Context:
    """Create context containing a support message."""

    return Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={
                    "message": "I was charged twice.",
                },
                producer="test-suite",
            ),
        )
    )


def test_context_strategy_renders_prompt_before_model_call() -> None:
    model = RecordingLanguageModel(
        response_text="duplicate_charge",
    )
    strategy = create_strategy(language_model=model)

    context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={"message": "I was charged twice."},
                producer="test-suite",
            ),
        )
    )

    outcome = asyncio.run(strategy.run(context))

    assert model.received_prompt == Prompt(text="Classify: I was charged twice.")
    assert outcome.output == "duplicate_charge"
    assert outcome.metrics is not None
    assert outcome.metrics.provider == "test-provider"
    assert outcome.metrics.model == "test-model"
    assert outcome.metrics.prompt_tokens == 10
    assert outcome.metrics.completion_tokens == 2
    assert outcome.metrics.total_tokens == 12
    assert outcome.metrics.latency_ms == 15
    assert outcome.metrics.estimated_cost_usd == 0.0001


def test_context_strategy_exposes_metadata_and_template() -> None:
    model = RecordingLanguageModel(
        response_text="duplicate_charge",
    )
    strategy = create_strategy(language_model=model)

    assert strategy.metadata.name == "Classify support message"
    assert strategy.template.text == "Classify: {message}"


async def execute_strategy(
    strategy: Strategy,
    context: Context,
) -> str:
    """Execute through the common strategy protocol."""

    outcome = await strategy.run(context)

    assert isinstance(outcome.output, str)

    return outcome.output


def test_context_strategy_satisfies_strategy_protocol() -> None:
    strategy = create_strategy(
        language_model=RecordingLanguageModel(
            response_text="duplicate_charge",
        )
    )
    context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={"message": "I was charged twice."},
                producer="test-suite",
            ),
        )
    )

    output = asyncio.run(
        execute_strategy(
            strategy=strategy,
            context=context,
        )
    )

    assert output == "duplicate_charge"


def test_context_strategy_exposes_model_requirements() -> None:
    requirements = ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.TOOL_USE,
            }
        ),
        minimum_context_window_tokens=100_000,
    )

    strategy = ContextPromptStrategy(
        metadata=StrategyMetadata(
            name="Context-aware support strategy",
            description="Classify support messages from context.",
            version="1.0.0",
        ),
        template=PromptTemplate(
            text="Classify: {message}",
            bindings=(
                PromptBinding(
                    variable_name="message",
                    event_type="customer.message.received",
                    field_name="message",
                ),
            ),
        ),
        language_model=RecordingLanguageModel(
            response_text="duplicate_charge",
        ),
        model_requirements=requirements,
    )

    assert strategy.model_requirements == requirements


def test_context_strategy_allows_omitted_model_requirements() -> None:
    strategy = create_strategy(
        language_model=RecordingLanguageModel(
            response_text="duplicate_charge",
        )
    )

    assert strategy.model_requirements is None


def test_context_strategy_exposes_model_binding() -> None:
    binding = ModelBinding(
        identifier="provider-a/model-small",
    )

    strategy = ContextPromptStrategy(
        metadata=StrategyMetadata(
            name="Context-aware classification",
            description="Classify a support request from context.",
            version="1.0.0",
        ),
        template=PromptTemplate(
            text="Classify: {message}",
            bindings=(
                PromptBinding(
                    variable_name="message",
                    event_type="customer.message.received",
                    field_name="message",
                ),
            ),
        ),
        language_model=RecordingLanguageModel(
            response_text="duplicate_charge",
        ),
        model_binding=binding,
    )

    assert strategy.model_binding == binding


def test_context_strategy_allows_omitted_model_binding() -> None:
    strategy = create_strategy(
        language_model=RecordingLanguageModel(
            response_text="duplicate_charge",
        )
    )

    assert strategy.model_binding is None


def test_context_strategy_accepts_matching_model_binding() -> None:
    model = RecordingLanguageModel(
        provider="provider-a",
        model="small",
        response_text="duplicate_charge",
    )
    strategy = create_strategy(
        language_model=model,
        model_binding=ModelBinding(
            identifier="provider-a/small",
        ),
    )

    outcome = asyncio.run(strategy.run(create_context()))

    assert model.received_prompt == Prompt(text="Classify: I was charged twice.")
    assert outcome.output == "duplicate_charge"
    assert outcome.metrics is not None
    assert outcome.metrics.provider == "provider-a"
    assert outcome.metrics.model == "small"


def test_context_strategy_rejects_mismatched_model_binding() -> None:
    model = RecordingLanguageModel(
        provider="provider-b",
        model="large",
        response_text="duplicate_charge",
    )
    strategy = create_strategy(
        language_model=model,
        model_binding=ModelBinding(
            identifier="provider-a/small",
        ),
    )

    with pytest.raises(
        ModelBindingMismatchError,
        match="provider-b/large",
    ):
        asyncio.run(strategy.run(create_context()))


def test_context_strategy_rejects_response_from_different_model() -> None:
    model = RecordingLanguageModel(
        provider="provider-a",
        model="large",
        response_text="duplicate_charge",
    )
    strategy = create_strategy(
        language_model=model,
        model_binding=ModelBinding(
            identifier="provider-a/small",
        ),
    )

    with pytest.raises(
        ModelBindingMismatchError,
        match="provider-a/large",
    ):
        asyncio.run(strategy.run(create_context()))


def test_context_strategy_executes_without_model_binding() -> None:
    model = RecordingLanguageModel(
        provider="provider-any",
        model="model-any",
        response_text="duplicate_charge",
    )
    strategy = create_strategy(
        language_model=model,
    )

    outcome = asyncio.run(strategy.run(create_context()))

    assert outcome.output == "duplicate_charge"

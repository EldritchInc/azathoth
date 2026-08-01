"""Tests for language-model-backed prompt strategies."""

import asyncio
from uuid import UUID

from azathoth.context import Context
from azathoth.prompting import PromptStrategy
from azathoth.providers import ModelResponse, Prompt
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

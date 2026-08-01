"""Integration tests for prompt strategy execution."""

import asyncio

from azathoth.context import Context
from azathoth.execution import StrategyExecutor
from azathoth.prompting import PromptStrategy
from azathoth.providers import ModelResponse, Prompt
from azathoth.strategies import StrategyMetadata


class StubLanguageModel:
    """A deterministic language model used by integration tests."""

    async def complete(self, prompt: Prompt) -> ModelResponse:
        """Return a fixed model response."""

        return ModelResponse(
            text="duplicate_charge",
            provider="test",
            model="stub",
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
            latency_ms=15,
            estimated_cost_usd=0.0001,
        )


def test_executor_runs_prompt_strategy() -> None:
    strategy = PromptStrategy(
        metadata=StrategyMetadata(
            name="Classify support request",
            description="Classify a support request with a language model.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text="Classify the supplied support request.",
        ),
        language_model=StubLanguageModel(),
    )

    result = asyncio.run(
        StrategyExecutor().execute(
            strategy=strategy,
            context=Context(),
        )
    )

    assert result.output == "duplicate_charge"

    assert tuple(event.event_type for event in result.final_context.events) == (
        "strategy.execution.started",
        "strategy.execution.completed",
    )

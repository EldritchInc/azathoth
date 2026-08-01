"""End-to-end optimization tests for context-aware prompting."""

import asyncio

from azathoth.context import Context, ContextEvent
from azathoth.evaluation import (
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.goals import Goal
from azathoth.optimization import (
    OptimizationExample,
    OptimizationRunner,
)
from azathoth.prompting import (
    ContextPromptStrategy,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import ModelResponse, Prompt
from azathoth.strategies import StrategyMetadata


class StubLanguageModel:
    """A deterministic language model for optimization testing."""

    async def complete(self, prompt: Prompt) -> ModelResponse:
        """Return the expected support category."""

        return ModelResponse(
            text="duplicate_charge",
        )


def test_context_prompt_strategy_runs_through_optimization_pipeline() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={"message": "I was charged twice."},
                producer="support-api",
            ),
        )
    )

    example = OptimizationExample(
        name="Duplicate charge classification",
        goal=Goal(
            name="Classify support intent",
            description="Identify the support category.",
            success_criteria=("The predicted category matches the expected category.",),
        ),
        context=context,
        expected_outcome=ExpectedOutcome(
            description="The request is classified as a duplicate charge.",
            value="duplicate_charge",
            comparison=OutcomeComparison.EXACT,
        ),
    )

    strategy = ContextPromptStrategy(
        metadata=StrategyMetadata(
            name="Context-aware support classification",
            description="Classify a support message rendered from context.",
            version="1.0.0",
        ),
        template=PromptTemplate(
            text=("Classify this support message:\n{customer_message}"),
            bindings=(
                PromptBinding(
                    variable_name="customer_message",
                    event_type="customer.message.received",
                    field_name="message",
                ),
            ),
        ),
        language_model=StubLanguageModel(),
    )

    run = asyncio.run(
        OptimizationRunner().run(
            example=example,
            strategy=strategy,
            evaluator=ExactMatchEvaluator(),
        )
    )

    assert run.passed is True
    assert run.execution.output == "duplicate_charge"
    assert run.evaluation.passed is True

"""Tests for discovering models from prompt strategy requirements."""

from azathoth.prompting import (
    PromptStrategy,
)
from azathoth.providers import (
    ModelCapability,
    ModelCatalog,
    ModelMetadata,
    ModelQuery,
    ModelRequirements,
    ModelResponse,
    Prompt,
)
from azathoth.strategies import StrategyMetadata


class StubLanguageModel:
    """A model dependency used only to construct the prompt strategy."""

    async def complete(self, prompt: Prompt) -> ModelResponse:
        """Return a deterministic response."""

        return ModelResponse(
            text="unused",
            provider="stub",
            model="stub",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            latency_ms=1,
            estimated_cost_usd=0.0,
        )


def test_prompt_strategy_requirements_discover_eligible_models() -> None:
    catalog = ModelCatalog(
        models=(
            ModelMetadata(
                provider="provider-a",
                model="structured",
                display_name="Structured Model",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                context_window_tokens=128_000,
            ),
            ModelMetadata(
                provider="provider-b",
                model="plain",
                display_name="Plain Model",
                context_window_tokens=128_000,
            ),
        )
    )

    strategy = PromptStrategy(
        metadata=StrategyMetadata(
            name="Structured response strategy",
            description="Return a structured response.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text="Return structured output.",
        ),
        language_model=StubLanguageModel(),
        model_requirements=ModelRequirements(
            required_capabilities=frozenset(
                {
                    ModelCapability.STRUCTURED_OUTPUT,
                }
            ),
            minimum_context_window_tokens=100_000,
        ),
    )

    assert strategy.model_requirements is not None

    eligible = catalog.find(ModelQuery.from_requirements(strategy.model_requirements))

    assert tuple(model.identifier for model in eligible) == ("provider-a/structured",)

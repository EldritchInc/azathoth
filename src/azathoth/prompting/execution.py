"""Shared execution behavior for language-model-backed strategies."""

from azathoth.prompting.models import ModelBinding
from azathoth.providers import LanguageModel, Prompt
from azathoth.strategies import (
    StrategyExecutionMetrics,
    StrategyOutcome,
)


async def execute_prompt(
    *,
    prompt: Prompt,
    language_model: LanguageModel,
    model_binding: ModelBinding | None,
) -> StrategyOutcome:
    """Execute a prompt and translate its response into a strategy outcome."""

    response = await language_model.complete(prompt)

    if model_binding is not None:
        model_binding.validate_response(response)

    return StrategyOutcome(
        output=response.text,
        metrics=StrategyExecutionMetrics(
            provider=response.provider,
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            latency_ms=response.latency_ms,
            estimated_cost_usd=response.estimated_cost_usd,
        ),
    )

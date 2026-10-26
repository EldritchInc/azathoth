"""Shared execution behavior for language-model-backed strategies."""

import json

from pydantic import JsonValue

from azathoth.prompting.exceptions import PromptOutputFormatError
from azathoth.prompting.models import ModelBinding
from azathoth.prompting.output_format import PromptOutputFormat, parse_json_reply
from azathoth.providers import LanguageModel, Prompt
from azathoth.strategies import (
    StrategyExecutionMetrics,
    StrategyOutcome,
    StrategyResourceBinding,
)


async def execute_prompt(
    *,
    prompt: Prompt,
    language_model: LanguageModel,
    model_binding: ModelBinding | None,
    output_format: PromptOutputFormat = PromptOutputFormat.TEXT,
    strategy_name: str | None = None,
) -> StrategyOutcome:
    """Execute a prompt and translate its response into a strategy outcome.

    With JSON output, the reply is parsed into the outcome's output.

    Raises:
        ModelBindingMismatchError: The response came from another model.
        PromptOutputFormatError: The reply is not valid JSON when JSON output
            is declared.
    """

    response = await language_model.complete(prompt)

    if model_binding is not None:
        model_binding.validate_response(response)

    output: JsonValue = response.text

    if output_format is PromptOutputFormat.JSON:
        try:
            output = parse_json_reply(response.text)
        except json.JSONDecodeError as exc:
            if strategy_name is None:
                message = f"Prompt reply is not valid JSON: {exc.msg}."
            else:
                message = f"Prompt strategy {strategy_name!r} replied with invalid JSON: {exc.msg}."

            raise PromptOutputFormatError(message) from exc

    return StrategyOutcome(
        output=output,
        resources=(
            (
                StrategyResourceBinding(
                    kind="model",
                    identifier=model_binding.identifier,
                ),
            )
            if model_binding is not None
            else ()
        ),
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

"""Language-model-backed prompt strategies."""

from azathoth.context import Context
from azathoth.prompting.models import ModelBinding
from azathoth.providers import (
    LanguageModel,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import (
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome
)


class PromptStrategy:
    """Execute a rendered prompt using a language model."""

    def __init__(
        self,
        *,
        metadata: StrategyMetadata,
        prompt: Prompt,
        language_model: LanguageModel,
        model_requirements: ModelRequirements | None = None,
        model_binding: ModelBinding | None = None,
    ) -> None:
        self._metadata = metadata
        self._prompt = prompt
        self._language_model = language_model
        self._model_requirements = model_requirements
        self._model_binding = model_binding

    @property
    def metadata(self) -> StrategyMetadata:
        """Return stable identifying metadata for this strategy."""

        return self._metadata

    @property
    def prompt(self) -> Prompt:
        """Return the rendered prompt executed by this strategy."""

        return self._prompt
    
    @property
    def model_requirements(self) -> ModelRequirements | None:
        """Return the requirements declared for the backing model."""

        return self._model_requirements
    
    @property
    def model_binding(self) -> ModelBinding | None:
        """Return the catalog model bound to this strategy."""

        return self._model_binding

    async def run(self, context: Context) -> StrategyOutcome:
        """Execute the prompt and return the model response text."""

        response = await self._language_model.complete(self._prompt)
        
        if self._model_binding is not None:
            self._model_binding.validate_response(response)

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

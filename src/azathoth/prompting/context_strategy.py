"""Context-aware language-model-backed strategies."""

from azathoth.context import Context
from azathoth.prompting.models import PromptTemplate
from azathoth.providers import LanguageModel, ModelRequirements
from azathoth.strategies import (
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome,
)


class ContextPromptStrategy:
    """Render a prompt from context and execute it with a language model."""

    def __init__(
        self,
        *,
        metadata: StrategyMetadata,
        template: PromptTemplate,
        language_model: LanguageModel,
        model_requirements: ModelRequirements | None = None,
    ) -> None:
        self._metadata = metadata
        self._template = template
        self._language_model = language_model
        self._model_requirements = model_requirements

    @property
    def metadata(self) -> StrategyMetadata:
        """Return stable identifying metadata for this strategy."""

        return self._metadata

    @property
    def template(self) -> PromptTemplate:
        """Return the context-aware prompt template."""

        return self._template
    
    @property
    def model_requirements(self) -> ModelRequirements | None:
        """Return the requirements declared for the backing model."""

        return self._model_requirements

    async def run(self, context: Context) -> StrategyOutcome:
        """Render and execute the prompt against the supplied context."""

        prompt = self._template.render(context)
        prompt = self._template.render(context)
        response = await self._language_model.complete(prompt)

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
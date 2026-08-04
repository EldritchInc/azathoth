"""Context-aware language-model-backed strategies."""

from azathoth.context import Context
from azathoth.prompting.execution import execute_prompt
from azathoth.prompting.models import ModelBinding, PromptTemplate
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
        model_binding: ModelBinding | None = None,
    ) -> None:
        self._metadata = metadata
        self._template = template
        self._language_model = language_model
        self._model_requirements = model_requirements
        self._model_binding = model_binding

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
    
    @property
    def model_binding(self) -> ModelBinding | None:
        """Return the catalog model bound to this strategy."""

        return self._model_binding

    async def run(self, context: Context) -> StrategyOutcome:
        """Render and execute the prompt against the supplied context."""

        prompt = self._template.render(context)

        return await execute_prompt(
            prompt=prompt,
            language_model=self._language_model,
            model_binding=self._model_binding,
        )
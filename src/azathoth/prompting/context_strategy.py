"""Context-aware language-model-backed strategies."""

from azathoth.context import Context
from azathoth.prompting.models import PromptTemplate
from azathoth.providers import LanguageModel
from azathoth.strategies import StrategyMetadata, StrategyOutcome


class ContextPromptStrategy:
    """Render a prompt from context and execute it with a language model."""

    def __init__(
        self,
        *,
        metadata: StrategyMetadata,
        template: PromptTemplate,
        language_model: LanguageModel,
    ) -> None:
        self._metadata = metadata
        self._template = template
        self._language_model = language_model

    @property
    def metadata(self) -> StrategyMetadata:
        """Return stable identifying metadata for this strategy."""

        return self._metadata

    @property
    def template(self) -> PromptTemplate:
        """Return the context-aware prompt template."""

        return self._template

    async def run(self, context: Context) -> StrategyOutcome:
        """Render and execute the prompt against the supplied context."""

        prompt = self._template.render(context)
        response = await self._language_model.complete(prompt)

        return StrategyOutcome(
            output=response.text,
        )
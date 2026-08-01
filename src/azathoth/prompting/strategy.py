"""Language-model-backed prompt strategies."""

from azathoth.context import Context
from azathoth.providers import LanguageModel, Prompt
from azathoth.strategies import StrategyMetadata, StrategyOutcome


class PromptStrategy:
    """Execute a rendered prompt using a language model."""

    def __init__(
        self,
        *,
        metadata: StrategyMetadata,
        prompt: Prompt,
        language_model: LanguageModel,
    ) -> None:
        self._metadata = metadata
        self._prompt = prompt
        self._language_model = language_model

    @property
    def metadata(self) -> StrategyMetadata:
        """Return stable identifying metadata for this strategy."""

        return self._metadata

    @property
    def prompt(self) -> Prompt:
        """Return the rendered prompt executed by this strategy."""

        return self._prompt

    async def run(self, context: Context) -> StrategyOutcome:
        """Execute the prompt and return the model response text."""

        response = await self._language_model.complete(self._prompt)

        return StrategyOutcome(
            output=response.text,
        )
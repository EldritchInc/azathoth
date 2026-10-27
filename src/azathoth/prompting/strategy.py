"""Language-model-backed prompt strategies."""

from azathoth.context import Context
from azathoth.prompting.execution import execute_prompt
from azathoth.prompting.models import ModelBinding
from azathoth.prompting.output_format import PromptOutputFormat
from azathoth.providers import (
    LanguageModel,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata, StrategyOutcome


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
        output_format: PromptOutputFormat = PromptOutputFormat.TEXT,
    ) -> None:
        self._metadata = metadata
        self._prompt = prompt
        self._language_model = language_model
        self._model_requirements = model_requirements
        self._model_binding = model_binding
        self._output_format = output_format

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

    @property
    def output_format(self) -> PromptOutputFormat:
        """Return how the model's reply becomes this strategy's output."""

        return self._output_format

    async def run(self, _context: Context) -> StrategyOutcome:
        """Execute the prompt and return the model response."""

        return await execute_prompt(
            prompt=self._prompt,
            language_model=self._language_model,
            model_binding=self._model_binding,
            output_format=self._output_format,
            strategy_name=self._metadata.name,
        )

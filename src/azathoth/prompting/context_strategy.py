"""Context-aware language-model-backed strategies."""

from azathoth.context import Context
from azathoth.prompting.execution import execute_prompt
from azathoth.prompting.models import ModelBinding, PromptTemplate
from azathoth.prompting.output_format import PromptOutputFormat
from azathoth.providers import (
    CONTENT_MODALITIES,
    LanguageModel,
    ModelModality,
    ModelRequirements,
    Prompt,
    PromptContentError,
)
from azathoth.strategies import (
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
        output_format: PromptOutputFormat = PromptOutputFormat.TEXT,
        model_input_modalities: frozenset[ModelModality] | None = None,
    ) -> None:
        self._metadata = metadata
        self._template = template
        self._language_model = language_model
        self._model_requirements = model_requirements
        self._model_binding = model_binding
        self._output_format = output_format
        self._model_input_modalities = model_input_modalities

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

    @property
    def output_format(self) -> PromptOutputFormat:
        """Return how the model's reply becomes this strategy's output."""

        return self._output_format

    @property
    def model_input_modalities(self) -> frozenset[ModelModality] | None:
        """Return the input modalities the bound model's catalog entry says it takes."""

        return self._model_input_modalities

    async def run(self, context: Context) -> StrategyOutcome:
        """Render and execute the prompt against the supplied context.

        Raises:
            PromptContentError: The prompt shows content of a modality the
                bound model does not take; the model is not called.
        """

        prompt = self._template.render(context)
        self._require_readable_content(prompt)

        return await execute_prompt(
            prompt=prompt,
            language_model=self._language_model,
            model_binding=self._model_binding,
            output_format=self._output_format,
            strategy_name=self._metadata.name,
        )

    def _require_readable_content(
        self,
        prompt: Prompt,
    ) -> None:
        """Refuse content the bound model's catalog entry says it cannot read (ADR 0115)."""

        if self._model_input_modalities is None or self._model_binding is None:
            return

        for content in prompt.contents():
            modality = CONTENT_MODALITIES[content.media_type]

            if modality not in self._model_input_modalities:
                raise PromptContentError(
                    f"Prompt strategy {self._metadata.name!r} shows content {content.digest} "
                    f"as {content.media_type}, but model {self._model_binding.identifier} "
                    f"does not take {modality} input."
                )

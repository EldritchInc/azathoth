"""Context-aware language-model-backed strategies."""

import asyncio

from azathoth.context import Context, active_step_lineage
from azathoth.prompting.citations import CitationPolicy, CitedSource, check_citations
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
from azathoth.tools.content import active_tool_content, received_origin


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
        citations: CitationPolicy | None = None,
    ) -> None:
        self._metadata = metadata
        self._template = template
        self._language_model = language_model
        self._model_requirements = model_requirements
        self._model_binding = model_binding
        self._output_format = output_format
        self._model_input_modalities = model_input_modalities
        self._citations = citations

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

    @property
    def citations(self) -> CitationPolicy | None:
        """Return how the step treats what its reply cites, when it is a cited step."""

        return self._citations

    async def run(self, context: Context) -> StrategyOutcome:
        """Render and execute the prompt against the supplied context.

        A cited step's reply has every citation checked and replaced by its
        check, and the checks kept and recorded as a resource (ADR 0116).

        Raises:
            PromptContentError: The prompt shows content of a modality the
                bound model does not take; the model is not called. Or a cited
                step's run has no content store to keep its checks in.
            CitationCheckError: A cited step's reply cites a source its prompt
                did not show, or, under `fail`, what the source does not hold.
        """

        prompt, shown = self._template.render_with_sources(
            context,
            strategy_name=self._metadata.name,
        )
        self._require_readable_content(prompt)

        outcome = await execute_prompt(
            prompt=prompt,
            language_model=self._language_model,
            model_binding=self._model_binding,
            output_format=self._output_format,
            strategy_name=self._metadata.name,
        )

        if self._citations is None:
            return outcome

        access = active_tool_content()
        step = active_step_lineage()

        if access is None or step is None:
            raise PromptContentError(
                f"Prompt strategy {self._metadata.name!r} checks citations, which this run "
                "cannot keep: it has no content store."
            )

        sources = {
            variable: CitedSource(
                segmented=segmented,
                origin=received_origin(
                    segmented.source_digest,
                    step.step.run_id,
                    initial_context=access.initial_context,
                ),
            )
            for variable, segmented in shown.items()
        }
        output, record = await asyncio.to_thread(
            check_citations,
            outcome.output,
            sources=sources,
            policy=self._citations,
            store=access.store,
            strategy_name=self._metadata.name,
        )

        return outcome.model_copy(
            update={"output": output, "resources": (*outcome.resources, record)},
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

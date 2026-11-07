"""Tests that a model is shown only content its catalog entry says it reads (ADR 0115)."""

import asyncio
import json
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.inputs import (
    BINARY_MEDIA_TYPES,
    ContentRef,
    InMemoryContentStore,
    InputProvenance,
    ResolvedInput,
    content_bytes_digest,
)
from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    FixedModelSelection,
    ModelBinding,
    PortfolioModelSelection,
    PromptBinding,
    PromptTemplate,
    generate_context_prompt_candidates,
)
from azathoth.providers import (
    CONTENT_MODALITIES,
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelModality,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelRequirements,
    ModelResponse,
    Prompt,
    PromptContentError,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import ToolContentAccess
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowStepStatus,
    create_workflow_input_events,
)

WORKFLOW_ID = UUID("c1520000-0000-4000-8000-000000000001")

STEP_ID = UUID("c1520000-0000-4000-8000-000000000002")

STRATEGY_ID = UUID("c1520000-0000-4000-8000-000000000003")

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

TEXT_ONLY = "test/text-only"

SEEING = "test/seeing"

READING = "test/reading"

TEMPLATE = PromptTemplate(
    text="Describe this:\n{document}",
    bindings=(
        PromptBinding(
            variable_name="document",
            event_type="workflow.input.received",
            field_name="input",
        ),
    ),
)

METADATA = StrategyMetadata(
    id=STRATEGY_ID,
    name="describe",
    description="Describe what the workflow was given.",
    version="1.0.0",
)


def model(
    identifier: str,
    *inputs: ModelModality,
) -> ModelMetadata:
    """Return a catalog entry for one test model that takes some input modalities."""

    provider, name = identifier.split("/")

    return ModelMetadata(
        provider=provider,
        model=name,
        display_name=name,
        input_modalities=frozenset({ModelModality.TEXT, *inputs}),
    )


CATALOG = ModelCatalog(
    models=(
        model(TEXT_ONLY),
        model(SEEING, ModelModality.IMAGE),
        model(READING, ModelModality.IMAGE, ModelModality.FILE),
    )
)

PORTFOLIO = ModelPortfolio(
    entries=tuple(
        ModelPortfolioEntry(provider=entry.provider, model=entry.model) for entry in CATALOG.models
    )
)


class RecordingModel:
    """A language model that records the prompts it is sent."""

    def __init__(
        self,
        identifier: str,
    ) -> None:
        self.identifier = identifier
        self.prompts: list[Prompt] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record the prompt, and answer as the deterministic model does."""

        self.prompts.append(prompt)
        provider, name = self.identifier.split("/")

        return await DeterministicLanguageModel(
            provider=provider,
            model=name,
            response_text="Described.",
        ).complete(prompt)


def registry() -> tuple[LanguageModelRegistry, dict[str, RecordingModel]]:
    """Return a registry of a recording model for every catalog entry, and the models."""

    models = {entry.identifier: RecordingModel(entry.identifier) for entry in CATALOG.models}

    return LanguageModelRegistry(models=dict(models)), models


def received(
    content: bytes,
    media_type: str,
) -> Context:
    """Return a run's initial context that received one piece of content."""

    digest = content_bytes_digest(content)

    return Context(
        events=tuple(
            create_workflow_input_events(
                ResolvedInput(
                    value=ContentRef(
                        digest=digest,
                        media_type=media_type,
                        size_bytes=len(content),
                    ).to_value(),
                    media_type=media_type,
                    provenance=InputProvenance(
                        uri="file:///claims/claim-0412",
                        media_type=media_type,
                        size_bytes=len(content),
                        digest=digest,
                    ),
                ),
                producer="azathoth.cli",
            )
        )
    )


def run(
    strategy: ContextPromptStrategy,
    content: bytes,
    media_type: str,
) -> tuple[WorkflowStepStatus, str]:
    """Run one step of a strategy over a run given some content; return its status and record."""

    initial = received(content, media_type)
    store = InMemoryContentStore()
    store.put(content)
    workflow = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Describe a document",
            description="Show a model the workflow's input.",
            version="1.0.0",
        ),
        steps=(WorkflowCandidateStep(id=STEP_ID, strategy=strategy),),
    )
    result = asyncio.run(
        WorkflowRunner(
            content=ToolContentAccess(store=store, initial_context=lambda run_id: initial),
        ).run_recording_failures(workflow, initial)
    )

    return result.steps[0].status, json.dumps(result.model_dump(mode="json"))


def candidates(
    specification: ContextPromptStrategySpec,
) -> tuple[tuple[ContextPromptStrategy, ...], dict[str, RecordingModel]]:
    """Return the candidates a specification generates over the test catalog."""

    language_models, models = registry()

    return (
        generate_context_prompt_candidates(
            specification,
            CATALOG,
            language_models,
            portfolio=PORTFOLIO,
        ),
        models,
    )


def fixed(
    identifier: str,
) -> ContextPromptStrategySpec:
    """Return the specification of the describing step, fixed to one model."""

    provider, name = identifier.split("/")

    return ContextPromptStrategySpec(
        metadata=METADATA,
        template=TEMPLATE,
        model_selection=FixedModelSelection(provider=provider, model=name),
    )


def test_every_binary_media_type_has_a_modality() -> None:
    assert set(CONTENT_MODALITIES) == set(BINARY_MEDIA_TYPES)
    assert dict(CONTENT_MODALITIES) == {
        "application/pdf": ModelModality.FILE,
        "image/png": ModelModality.IMAGE,
        "image/jpeg": ModelModality.IMAGE,
        "image/webp": ModelModality.IMAGE,
    }


def test_a_candidate_carries_its_models_input_modalities_from_the_catalog() -> None:
    (strategy,), _ = candidates(fixed(READING))

    assert strategy.model_input_modalities == frozenset(
        {ModelModality.TEXT, ModelModality.IMAGE, ModelModality.FILE}
    )


def test_a_model_that_reads_files_is_shown_a_pdf() -> None:
    (strategy,), models = candidates(fixed(READING))

    status, _ = run(strategy, PDF, "application/pdf")

    assert status is WorkflowStepStatus.EXECUTED
    assert models[READING].prompts[0].contents()[0].digest == content_bytes_digest(PDF)


def test_a_model_that_sees_images_is_shown_an_image() -> None:
    (strategy,), models = candidates(fixed(SEEING))

    status, _ = run(strategy, PNG, "image/png")

    assert status is WorkflowStepStatus.EXECUTED
    assert len(models[SEEING].prompts) == 1


@pytest.mark.parametrize(
    ("identifier", "content", "media_type", "modality"),
    [
        pytest.param(TEXT_ONLY, PDF, "application/pdf", "file", id="text-model-pdf"),
        pytest.param(TEXT_ONLY, PNG, "image/png", "image", id="text-model-image"),
        pytest.param(SEEING, PDF, "application/pdf", "file", id="vision-model-pdf"),
    ],
)
def test_content_a_model_does_not_read_fails_the_step_before_it_is_called(
    identifier: str,
    content: bytes,
    media_type: str,
    modality: str,
) -> None:
    (strategy,), models = candidates(fixed(identifier))

    status, recorded = run(strategy, content, media_type)

    assert status is WorkflowStepStatus.FAILED
    assert (
        f"Prompt strategy 'describe [{identifier}]' shows content "
        f"{content_bytes_digest(content)} as {media_type}, but model {identifier} "
        f"does not take {modality} input."
    ) in recorded
    assert models[identifier].prompts == []


def test_declared_requirements_choose_only_models_that_read_what_the_step_shows() -> None:
    specification = ContextPromptStrategySpec(
        metadata=METADATA,
        template=TEMPLATE,
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(
                required_input_modalities=frozenset({ModelModality.TEXT, ModelModality.FILE}),
            ),
        ),
    )

    generated, _ = candidates(specification)

    assert [strategy.model_binding for strategy in generated] == [ModelBinding(identifier=READING)]


def test_a_prompt_of_text_needs_no_modality_beyond_text() -> None:
    (strategy,), models = candidates(
        ContextPromptStrategySpec(
            metadata=METADATA,
            template=PromptTemplate(text="Say hello."),
            model_selection=FixedModelSelection(provider="test", model="text-only"),
        )
    )

    status, _ = run(strategy, PDF, "application/pdf")

    assert status is WorkflowStepStatus.EXECUTED
    assert models[TEXT_ONLY].prompts == [Prompt(text="Say hello.")]


def test_a_strategy_built_without_catalog_modalities_is_not_checked() -> None:
    recording = RecordingModel(TEXT_ONLY)
    strategy = ContextPromptStrategy(
        metadata=METADATA,
        template=TEMPLATE,
        language_model=recording,
        model_binding=ModelBinding(identifier=TEXT_ONLY),
    )

    status, _ = run(strategy, PDF, "application/pdf")

    assert status is WorkflowStepStatus.EXECUTED
    assert len(recording.prompts) == 1


def test_a_strategy_with_modalities_but_no_bound_model_is_not_checked() -> None:
    recording = RecordingModel(TEXT_ONLY)
    strategy = ContextPromptStrategy(
        metadata=METADATA,
        template=TEMPLATE,
        language_model=recording,
        model_input_modalities=frozenset({ModelModality.TEXT}),
    )

    status, _ = run(strategy, PDF, "application/pdf")

    assert status is WorkflowStepStatus.EXECUTED
    assert len(recording.prompts) == 1


def test_the_refusal_is_a_prompt_content_error() -> None:
    (strategy,), _ = candidates(fixed(TEXT_ONLY))
    context = received(PDF, "application/pdf")

    with pytest.raises(PromptContentError):
        asyncio.run(strategy.run(context))

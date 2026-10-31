"""Tests for rebuilding a recorded workflow candidate from its signature."""

from uuid import UUID, uuid4, uuid5

import pytest

from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    FixedModelSelection,
    PortfolioModelSelection,
    PromptStrategy,
    PromptStrategySpec,
    PromptTemplate,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import ToolRequirement
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowCandidate,
    WorkflowCandidateRebuildError,
    WorkflowCandidateSignature,
    WorkflowGenerationError,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    generate_workflow_candidate,
    rebuild_workflow_candidate,
)
from tests.workflows.test_tool_generation import (
    create_implementation,
    create_implementation_resolver,
    create_tool_resolver,
)

WORKFLOW_ID = UUID("a0000000-0000-4000-8000-000000000001")

CLASSIFY_STEP_ID = UUID("a0000000-0000-4000-8000-000000000011")
SUMMARIZE_STEP_ID = UUID("a0000000-0000-4000-8000-000000000012")
PINNED_STEP_ID = UUID("a0000000-0000-4000-8000-000000000013")
COUNT_STEP_ID = UUID("a0000000-0000-4000-8000-000000000014")

CLASSIFY_STRATEGY_ID = UUID("a0000000-0000-4000-8000-000000000021")
SUMMARIZE_STRATEGY_ID = UUID("a0000000-0000-4000-8000-000000000022")
PINNED_STRATEGY_ID = UUID("a0000000-0000-4000-8000-000000000023")

REVISION = 2

EXPENSIVE_IDENTIFIER = "test/expensive"
CHEAP_IDENTIFIER = "test/cheap"


def create_metadata(
    strategy_id: UUID,
    name: str,
) -> StrategyMetadata:
    """Create deterministic strategy metadata."""

    return StrategyMetadata(
        id=strategy_id,
        name=name,
        description=f"{name} for candidate rebuild tests.",
    )


def create_specification() -> WorkflowSpecification:
    """Create a workflow with portfolio, context, pinned and tool steps."""

    portfolio_selection = PortfolioModelSelection(
        requirements=ModelRequirements(),
    )

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="candidate rebuild",
            description="Rebuild a measured candidate.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=CLASSIFY_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=create_metadata(CLASSIFY_STRATEGY_ID, "Classify"),
                    prompt=Prompt(text="Classify the request."),
                    model_selection=portfolio_selection,
                ),
            ),
            WorkflowStepSpecification(
                id=SUMMARIZE_STEP_ID,
                specification=ContextPromptStrategySpec(
                    metadata=create_metadata(SUMMARIZE_STRATEGY_ID, "Summarize"),
                    template=PromptTemplate(text="Summarize the request."),
                    model_selection=portfolio_selection,
                ),
            ),
            WorkflowStepSpecification(
                id=PINNED_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=create_metadata(PINNED_STRATEGY_ID, "Pinned"),
                    prompt=Prompt(text="Answer on the pinned model."),
                    model_selection=FixedModelSelection(
                        provider="test",
                        model="expensive",
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=COUNT_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="word_count",
                        version="1.0.0",
                        runtime="python",
                    ),
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create the expensive model first, so the configured candidate uses it."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="expensive",
                display_name="Expensive",
            ),
            ModelMetadata(
                provider="test",
                model="cheap",
                display_name="Cheap",
            ),
        ),
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable deterministic models for the whole catalog."""

    return LanguageModelRegistry(
        {
            EXPENSIVE_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model="expensive",
                response_text="expensive",
            ),
            CHEAP_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model="cheap",
                response_text="cheap",
            ),
        }
    )


def create_portfolio(
    *identifiers: str,
) -> ModelPortfolio:
    """Authorize the named models, or both models when none are named."""

    authorized = identifiers or (EXPENSIVE_IDENTIFIER, CHEAP_IDENTIFIER)

    return ModelPortfolio(
        entries=tuple(
            ModelPortfolioEntry(
                provider=identifier.partition("/")[0],
                model=identifier.partition("/")[2],
            )
            for identifier in authorized
        )
    )


def create_configured(
    *,
    revision: int = REVISION,
) -> WorkflowCandidate:
    """Generate the configured candidate promotion starts from."""

    return generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=create_portfolio(),
        tool_resolver=create_tool_resolver(),
        tool_implementation_resolver=create_implementation_resolver(
            create_implementation(),
        ),
        revision=revision,
    )


def measured_signature(
    *,
    cheap_steps: tuple[UUID, ...] = (),
    strategy_ids: dict[UUID, UUID] | None = None,
    workflow_id: UUID = WORKFLOW_ID,
    revision: int | None = REVISION,
) -> WorkflowCandidateSignature:
    """Return the configured signature with chosen steps on the cheap model.

    `strategy_ids` overrides individual steps' strategy IDs directly.
    """

    specification = create_specification()
    configured = create_configured()
    overrides = strategy_ids or {}

    step_strategy_ids = {
        step.id: step.specification.metadata.id
        for step in specification.steps
        if not isinstance(step.specification, ToolStepSpecification)
    }

    return WorkflowCandidateSignature(
        workflow_id=workflow_id,
        workflow_revision=revision,
        strategy_ids=tuple(
            overrides.get(
                step.id,
                (
                    uuid5(step_strategy_ids[step.id], CHEAP_IDENTIFIER)
                    if step.id in cheap_steps
                    else step.strategy.metadata.id
                ),
            )
            for step in configured.steps
        ),
    )


def rebuild(
    signature: WorkflowCandidateSignature,
    *,
    configured: WorkflowCandidate | None = None,
    portfolio: ModelPortfolio | None = None,
) -> WorkflowCandidate:
    """Rebuild a signature against the configured candidate."""

    return rebuild_workflow_candidate(
        specification=create_specification(),
        configured=create_configured() if configured is None else configured,
        signature=signature,
        catalog=create_catalog(),
        registry=create_registry(),
        portfolio=create_portfolio() if portfolio is None else portfolio,
    )


def model_identifier(
    candidate: WorkflowCandidate,
    step_id: UUID,
) -> str:
    """Return the model a candidate binds one prompt step to."""

    strategy = next(step.strategy for step in candidate.steps if step.id == step_id)

    assert isinstance(strategy, (PromptStrategy, ContextPromptStrategy))
    assert strategy.model_binding is not None

    return strategy.model_binding.identifier


def test_configured_candidate_uses_the_expensive_model() -> None:
    configured = create_configured()

    assert model_identifier(configured, CLASSIFY_STEP_ID) == EXPENSIVE_IDENTIFIER
    assert model_identifier(configured, SUMMARIZE_STEP_ID) == EXPENSIVE_IDENTIFIER


def test_rebuild_keeps_the_configured_candidate_when_it_was_measured() -> None:
    configured = create_configured()

    rebuilt = rebuild(configured.signature, configured=configured)

    assert rebuilt.signature == configured.signature
    assert all(
        rebuilt_step.strategy is configured_step.strategy
        for rebuilt_step, configured_step in zip(rebuilt.steps, configured.steps, strict=True)
    )


def test_rebuild_moves_one_prompt_step_to_its_measured_model() -> None:
    signature = measured_signature(cheap_steps=(CLASSIFY_STEP_ID,))

    rebuilt = rebuild(signature)

    assert rebuilt.signature == signature
    assert model_identifier(rebuilt, CLASSIFY_STEP_ID) == CHEAP_IDENTIFIER
    assert model_identifier(rebuilt, SUMMARIZE_STEP_ID) == EXPENSIVE_IDENTIFIER


def test_rebuild_moves_several_steps_including_context_prompts() -> None:
    signature = measured_signature(cheap_steps=(CLASSIFY_STEP_ID, SUMMARIZE_STEP_ID))

    rebuilt = rebuild(signature)

    assert rebuilt.signature == signature
    assert model_identifier(rebuilt, CLASSIFY_STEP_ID) == CHEAP_IDENTIFIER
    assert model_identifier(rebuilt, SUMMARIZE_STEP_ID) == CHEAP_IDENTIFIER


def test_rebuild_keeps_the_pinned_and_tool_steps() -> None:
    configured = create_configured()

    rebuilt = rebuild(
        measured_signature(cheap_steps=(CLASSIFY_STEP_ID,)),
        configured=configured,
    )

    configured_steps = {step.id: step for step in configured.steps}

    for step in rebuilt.steps:
        if step.id in {PINNED_STEP_ID, COUNT_STEP_ID}:
            assert step is configured_steps[step.id]


def test_rebuild_keeps_the_candidate_revision_and_result() -> None:
    configured = create_configured()

    rebuilt = rebuild(
        measured_signature(cheap_steps=(CLASSIFY_STEP_ID,)),
        configured=configured,
    )

    assert rebuilt.revision == REVISION
    assert rebuilt.result == configured.result
    assert rebuilt.metadata == configured.metadata


def test_rebuild_rejects_another_workflow() -> None:
    other = uuid4()

    with pytest.raises(
        WorkflowCandidateRebuildError,
        match=f"measured on workflow {other}, not workflow {WORKFLOW_ID}",
    ):
        rebuild(measured_signature(workflow_id=other))


def test_rebuild_rejects_a_signature_without_a_revision() -> None:
    with pytest.raises(
        WorkflowCandidateRebuildError,
        match="records no workflow revision",
    ):
        rebuild(measured_signature(revision=None))


def test_rebuild_rejects_another_revision() -> None:
    with pytest.raises(
        WorkflowCandidateRebuildError,
        match=f"measured on revision 1 of workflow {WORKFLOW_ID}, but its current revision is 2",
    ):
        rebuild(measured_signature(revision=1))


def test_rebuild_rejects_a_different_number_of_steps() -> None:
    signature = measured_signature()

    with pytest.raises(
        WorkflowCandidateRebuildError,
        match="The candidate has 3 steps, but revision 2",
    ):
        rebuild(
            signature.model_copy(
                update={"strategy_ids": signature.strategy_ids[:3]},
            )
        )


def test_rebuild_rejects_a_model_that_is_no_longer_authorized() -> None:
    with pytest.raises(
        WorkflowCandidateRebuildError,
        match=f"Workflow step {CLASSIFY_STEP_ID} cannot be rebuilt",
    ):
        rebuild(
            measured_signature(cheap_steps=(CLASSIFY_STEP_ID,)),
            portfolio=create_portfolio(EXPENSIVE_IDENTIFIER),
        )


def test_rebuild_rejects_a_pinned_step_on_another_model() -> None:
    with pytest.raises(
        WorkflowCandidateRebuildError,
        match=f"Workflow step {PINNED_STEP_ID} cannot be rebuilt",
    ):
        rebuild(measured_signature(cheap_steps=(PINNED_STEP_ID,)))


def test_rebuild_rejects_a_different_tool_strategy() -> None:
    with pytest.raises(
        WorkflowCandidateRebuildError,
        match=f"Workflow step {COUNT_STEP_ID} is a tool step",
    ):
        rebuild(measured_signature(strategy_ids={COUNT_STEP_ID: uuid4()}))


def test_rebuild_errors_are_generation_errors() -> None:
    assert issubclass(WorkflowCandidateRebuildError, WorkflowGenerationError)

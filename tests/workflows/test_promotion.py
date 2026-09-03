"""Tests for materializing workflow candidates as durable promotion configuration."""

from dataclasses import replace
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    FixedModelSelection,
    PortfolioModelSelection,
    PromptStrategy,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    InMemoryToolRepository,
    ToolCatalogLoader,
    ToolDefinition,
    ToolImplementation,
    ToolImplementationResolver,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
    ToolResolver,
)
from azathoth.workflows import (
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    ToolStepSpecification,
    WorkflowCandidate,
    WorkflowMetadata,
    WorkflowProductionModelSubstitution,
    WorkflowSpecification,
    WorkflowStepSpecification,
    materialize_workflow_candidate,
    promote_workflow_candidate,
)
from tests.model_authorization import generate_workflow_candidate

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

PROMPT_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

TOOL_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

TOOL_ID = UUID("55555555-5555-5555-5555-555555555555")

IMPLEMENTATION_ID = UUID("66666666-6666-6666-6666-666666666666")

MODEL_IDENTIFIER = "test/promoted-model"


def create_model_catalog() -> ModelCatalog:
    """Create deterministic model metadata."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="promoted-model",
                display_name="Promoted Model",
                context_window_tokens=8_192,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create one executable deterministic model."""

    return LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model="promoted-model",
                response_text="success",
            ),
        }
    )


def create_workflow() -> WorkflowSpecification:
    """Create a durable workflow with prompt and tool steps."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="promotion-workflow",
            description="Exercise candidate materialization.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=PROMPT_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="promotion-prompt",
                        description="Exercise prompt promotion.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=TOOL_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="promotion-tool",
                        version="1.0.0",
                        runtime="python",
                    ),
                ),
                depends_on=(PROMPT_STEP_ID,),
            ),
        ),
    )


def create_tool_repository() -> InMemoryToolRepository:
    """Create durable and executable tool configuration."""

    repository = InMemoryToolRepository()

    repository.save_definition(
        ToolDefinition(
            id=TOOL_ID,
            name="promotion-tool",
            description="Exercise tool preservation during promotion.",
            version="1.0.0",
            input_schema=ToolInputSchema(
                json_schema={
                    "type": "object",
                    "additionalProperties": False,
                }
            ),
            output_schema=ToolOutputSchema(
                json_schema={
                    "type": "object",
                }
            ),
        )
    )

    repository.save_implementation(
        ToolImplementation(
            id=IMPLEMENTATION_ID,
            tool_id=TOOL_ID,
            tool_version="1.0.0",
            version="1.0.0",
            runtime="python",
            source=("def run(inputs):\n    return inputs\n"),
        )
    )

    return repository


def create_candidate(
    specification: WorkflowSpecification,
) -> WorkflowCandidate:
    """Generate one executable workflow candidate."""

    loader = ToolCatalogLoader(
        create_tool_repository(),
    )

    return generate_workflow_candidate(
        specification=specification,
        catalog=create_model_catalog(),
        registry=create_registry(),
        tool_resolver=ToolResolver(
            loader.load_catalog(),
        ),
        tool_implementation_resolver=ToolImplementationResolver(
            loader.load_implementation_catalog(),
        ),
    )


def require_prompt(
    specification: WorkflowSpecification,
) -> PromptStrategySpec:
    """Return the deterministic prompt specification."""

    prompt = specification.steps[0].specification

    assert isinstance(
        prompt,
        PromptStrategySpec,
    )

    return prompt


def test_materialization_preserves_workflow_identity() -> None:
    specification = create_workflow()

    promoted = materialize_workflow_candidate(
        specification=specification,
        candidate=create_candidate(
            specification,
        ),
    )

    assert promoted.metadata == specification.metadata


def test_materialization_preserves_workflow_topology() -> None:
    specification = create_workflow()

    promoted = materialize_workflow_candidate(
        specification=specification,
        candidate=create_candidate(
            specification,
        ),
    )

    assert tuple(step.id for step in promoted.steps) == tuple(
        step.id for step in specification.steps
    )

    assert promoted.steps[1].depends_on == (PROMPT_STEP_ID,)


def test_materialization_pins_candidate_prompt_model() -> None:
    specification = create_workflow()

    promoted = materialize_workflow_candidate(
        specification=specification,
        candidate=create_candidate(
            specification,
        ),
    )

    prompt = require_prompt(
        promoted,
    )

    assert isinstance(
        prompt.model_selection,
        FixedModelSelection,
    )

    assert prompt.model_selection.identifier == MODEL_IDENTIFIER


def test_materialization_uses_candidate_model_binding() -> None:
    specification = create_workflow()

    candidate = create_candidate(
        specification,
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        PromptStrategy,
    )

    assert strategy.model_binding is not None

    promoted = materialize_workflow_candidate(
        specification=specification,
        candidate=candidate,
    )

    prompt = require_prompt(
        promoted,
    )

    assert isinstance(
        prompt.model_selection,
        FixedModelSelection,
    )

    assert prompt.model_selection.identifier == strategy.model_binding.identifier


def test_materialization_preserves_provider_native_model_path() -> None:
    specification = create_workflow()

    catalog = ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="organization/model",
                display_name="Nested Model",
                context_window_tokens=8_192,
            ),
        )
    )

    registry = LanguageModelRegistry(
        models={
            "test/organization/model": DeterministicLanguageModel(
                provider="test",
                model="organization/model",
                response_text="success",
            ),
        }
    )

    loader = ToolCatalogLoader(
        create_tool_repository(),
    )

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=catalog,
        registry=registry,
        tool_resolver=ToolResolver(
            loader.load_catalog(),
        ),
        tool_implementation_resolver=ToolImplementationResolver(
            loader.load_implementation_catalog(),
        ),
    )

    promoted = materialize_workflow_candidate(
        specification=specification,
        candidate=candidate,
    )

    prompt = require_prompt(
        promoted,
    )

    assert isinstance(
        prompt.model_selection,
        FixedModelSelection,
    )

    assert prompt.model_selection.provider == "test"
    assert prompt.model_selection.model == "organization/model"


def test_materialization_preserves_tool_requirement() -> None:
    specification = create_workflow()

    promoted = materialize_workflow_candidate(
        specification=specification,
        candidate=create_candidate(
            specification,
        ),
    )

    original_tool = specification.steps[1].specification
    promoted_tool = promoted.steps[1].specification

    assert isinstance(
        original_tool,
        ToolStepSpecification,
    )

    assert isinstance(
        promoted_tool,
        ToolStepSpecification,
    )

    assert promoted_tool == original_tool


def test_materialization_does_not_mutate_original_specification() -> None:
    specification = create_workflow()

    promoted = materialize_workflow_candidate(
        specification=specification,
        candidate=create_candidate(
            specification,
        ),
    )

    original_prompt = require_prompt(
        specification,
    )

    promoted_prompt = require_prompt(
        promoted,
    )

    assert isinstance(
        original_prompt.model_selection,
        PortfolioModelSelection,
    )

    assert isinstance(
        promoted_prompt.model_selection,
        FixedModelSelection,
    )


def test_materialization_rejects_different_step_identity() -> None:
    specification = create_workflow()

    candidate = create_candidate(
        specification,
    )

    replacement_step = replace(
        candidate.steps[1],
        id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )

    mismatched = replace(
        candidate,
        steps=(
            candidate.steps[0],
            replacement_step,
        ),
    )

    with pytest.raises(
        ValueError,
        match=("Workflow specification and candidate must contain the same step identifiers"),
    ):
        materialize_workflow_candidate(
            specification=specification,
            candidate=mismatched,
        )


def test_promotion_sets_active_production_state() -> None:
    specification = create_workflow()

    candidate = create_candidate(
        specification,
    )

    state_repository = InMemoryWorkflowProductionStateRepository()
    revision_repository = InMemoryWorkflowProductionRevisionRepository()

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=candidate,
        repository=state_repository,
        revision_repository=revision_repository,
    )

    assert state_repository.get(WORKFLOW_ID) == revision.state

    assert revision.state.specification.metadata.id == WORKFLOW_ID


def test_promotion_records_immutable_production_revision() -> None:
    specification = create_workflow()

    candidate = create_candidate(
        specification,
    )

    revision_repository = InMemoryWorkflowProductionRevisionRepository()

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=candidate,
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=revision_repository,
    )

    assert revision_repository.get(revision.id) is revision

    assert revision_repository.revisions() == (revision,)

    assert revision.workflow_id == WORKFLOW_ID


def test_promotion_pins_selected_candidate_model() -> None:
    specification = create_workflow()

    candidate = create_candidate(
        specification,
    )

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=candidate,
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    prompt = require_prompt(
        revision.state.specification,
    )

    assert isinstance(
        prompt.model_selection,
        FixedModelSelection,
    )

    assert prompt.model_selection.identifier == MODEL_IDENTIFIER


def test_promotion_preserves_explicit_model_substitutions() -> None:
    specification = create_workflow()

    substitution = WorkflowProductionModelSubstitution(
        step_id=PROMPT_STEP_ID,
        substitutes=(
            FixedModelSelection(
                provider="fallback-provider",
                model="first-fallback",
            ),
            FixedModelSelection(
                provider="fallback-provider",
                model="second-fallback",
            ),
        ),
    )

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=create_candidate(
            specification,
        ),
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
        model_substitutions=(substitution,),
    )

    assert revision.state.model_substitutions == (substitution,)


def test_promotion_replaces_active_state_and_preserves_revision_history() -> None:
    specification = create_workflow()

    candidate = create_candidate(
        specification,
    )

    state_repository = InMemoryWorkflowProductionStateRepository()
    revision_repository = InMemoryWorkflowProductionRevisionRepository()

    first = promote_workflow_candidate(
        specification=specification,
        candidate=candidate,
        repository=state_repository,
        revision_repository=revision_repository,
    )

    substitution = WorkflowProductionModelSubstitution(
        step_id=PROMPT_STEP_ID,
        substitutes=(
            FixedModelSelection(
                provider="fallback-provider",
                model="replacement-fallback",
            ),
        ),
    )

    second = promote_workflow_candidate(
        specification=specification,
        candidate=candidate,
        repository=state_repository,
        revision_repository=revision_repository,
        model_substitutions=(substitution,),
    )

    assert first.id != second.id

    assert first.state != second.state

    assert state_repository.states() == (second.state,)

    assert state_repository.get(WORKFLOW_ID) == second.state

    assert revision_repository.revisions_for_workflow(WORKFLOW_ID) == (
        first,
        second,
    )

    assert first.state.model_substitutions == ()

    assert second.state.model_substitutions == (substitution,)


def test_promotion_does_not_mutate_configured_workflow() -> None:
    specification = create_workflow()

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=create_candidate(
            specification,
        ),
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    configured_prompt = require_prompt(
        specification,
    )

    production_prompt = require_prompt(
        revision.state.specification,
    )

    assert isinstance(
        configured_prompt.model_selection,
        PortfolioModelSelection,
    )

    assert isinstance(
        production_prompt.model_selection,
        FixedModelSelection,
    )


def test_failed_promotion_does_not_replace_active_state_or_record_revision() -> None:
    specification = create_workflow()

    candidate = create_candidate(
        specification,
    )

    state_repository = InMemoryWorkflowProductionStateRepository()
    revision_repository = InMemoryWorkflowProductionRevisionRepository()

    existing = promote_workflow_candidate(
        specification=specification,
        candidate=candidate,
        repository=state_repository,
        revision_repository=revision_repository,
    )

    invalid_substitution = WorkflowProductionModelSubstitution(
        step_id=PROMPT_STEP_ID,
        substitutes=(
            FixedModelSelection(
                provider="test",
                model="promoted-model",
            ),
        ),
    )

    with pytest.raises(
        ValidationError,
        match=("Production model substitutes cannot include the step's primary model"),
    ):
        promote_workflow_candidate(
            specification=specification,
            candidate=candidate,
            repository=state_repository,
            revision_repository=revision_repository,
            model_substitutions=(invalid_substitution,),
        )

    assert state_repository.get(WORKFLOW_ID) == existing.state

    assert revision_repository.revisions() == (existing,)

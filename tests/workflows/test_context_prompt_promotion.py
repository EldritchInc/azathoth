"""Tests for promoting workflows whose prompt steps render from context."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
    ModelSelection,
    PortfolioModelSelection,
    PromptBinding,
    PromptOutputFormat,
    PromptStrategySpec,
    PromptTemplate,
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
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    WorkflowCandidate,
    WorkflowMetadata,
    WorkflowProductionModelSubstitution,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
    materialize_workflow_candidate,
    promote_workflow_candidate,
)
from tests.model_authorization import generate_workflow_candidate

WORKFLOW_ID = UUID("71000000-0000-4000-8000-000000000001")

STEP_ID = UUID("71000000-0000-4000-8000-000000000002")

STRATEGY_ID = UUID("71000000-0000-4000-8000-000000000003")

PRIMARY = FixedModelSelection(provider="test", model="context-model")

SUBSTITUTE = FixedModelSelection(provider="test", model="context-fallback")

TEMPLATE = PromptTemplate(
    text="Classify this text: {text}",
    bindings=(
        PromptBinding(
            variable_name="text",
            event_type=WORKFLOW_INPUT_EVENT_TYPE,
            field_name="input",
        ),
    ),
)


def create_catalog() -> ModelCatalog:
    """Create deterministic metadata for the context model."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="context-model",
                display_name="Context Model",
                context_window_tokens=8_192,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create the executable context model."""

    return LanguageModelRegistry(
        models={
            PRIMARY.identifier: DeterministicLanguageModel(
                provider="test",
                model="context-model",
                response_text='{"label": "positive"}',
            ),
        }
    )


def strategy_metadata() -> StrategyMetadata:
    """Return the shared prompt strategy identity."""

    return StrategyMetadata(
        id=STRATEGY_ID,
        name="classify text",
        description="Classify the workflow input.",
        version="1.0.0",
    )


def create_workflow(
    specification: ContextPromptStrategySpec | PromptStrategySpec,
) -> WorkflowSpecification:
    """Create a one-step workflow around one prompt specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="context promotion",
            description="Exercise promotion of context-prompt steps.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=specification,
                outputs=(WorkflowValueBinding(name="label"),),
            ),
        ),
        result=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="label",
        ),
    )


def context_specification(
    selection: ModelSelection,
) -> ContextPromptStrategySpec:
    """Return a JSON-replying context prompt with one model selection."""

    return ContextPromptStrategySpec(
        metadata=strategy_metadata(),
        template=TEMPLATE,
        model_selection=selection,
        output_format=PromptOutputFormat.JSON,
    )


def portfolio_workflow() -> WorkflowSpecification:
    """Create the configured workflow, selecting its model from the portfolio."""

    return create_workflow(
        context_specification(
            PortfolioModelSelection(requirements=ModelRequirements()),
        )
    )


def create_candidate(
    specification: WorkflowSpecification,
) -> WorkflowCandidate:
    """Generate the workflow's executable candidate."""

    return generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )


def materialized_step(
    specification: WorkflowSpecification,
) -> ContextPromptStrategySpec:
    """Return the only step's specification, requiring a context prompt."""

    step = specification.steps[0].specification

    assert isinstance(step, ContextPromptStrategySpec)

    return step


def test_materialization_pins_context_prompt_steps_to_their_candidate_model() -> None:
    specification = portfolio_workflow()

    promoted = materialize_workflow_candidate(
        specification=specification,
        candidate=create_candidate(specification),
    )

    assert materialized_step(promoted).model_selection == PRIMARY


def test_materialization_keeps_the_context_prompt_template_and_output_format() -> None:
    specification = portfolio_workflow()

    promoted = materialized_step(
        materialize_workflow_candidate(
            specification=specification,
            candidate=create_candidate(specification),
        )
    )

    assert promoted.metadata == strategy_metadata()
    assert promoted.template == TEMPLATE
    assert promoted.output_format is PromptOutputFormat.JSON


def test_materialization_rejects_a_context_prompt_step_with_a_fixed_prompt_candidate() -> None:
    fixed_prompt = create_workflow(
        PromptStrategySpec(
            metadata=strategy_metadata(),
            prompt=Prompt(text="Classify this text."),
            model_selection=PortfolioModelSelection(requirements=ModelRequirements()),
        )
    )

    with pytest.raises(
        ValueError,
        match="Context-prompt workflow steps must use ContextPromptStrategy candidates",
    ):
        materialize_workflow_candidate(
            specification=portfolio_workflow(),
            candidate=create_candidate(fixed_prompt),
        )


def test_materialization_rejects_a_fixed_prompt_step_with_a_context_prompt_candidate() -> None:
    fixed_prompt = create_workflow(
        PromptStrategySpec(
            metadata=strategy_metadata(),
            prompt=Prompt(text="Classify this text."),
            model_selection=PortfolioModelSelection(requirements=ModelRequirements()),
        )
    )

    with pytest.raises(
        ValueError,
        match="Prompt-backed workflow steps must use PromptStrategy candidates",
    ):
        materialize_workflow_candidate(
            specification=fixed_prompt,
            candidate=create_candidate(portfolio_workflow()),
        )


def test_promotion_sets_production_state_for_context_prompt_steps() -> None:
    specification = portfolio_workflow()

    state_repository = InMemoryWorkflowProductionStateRepository()
    revision_repository = InMemoryWorkflowProductionRevisionRepository()

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=create_candidate(specification),
        repository=state_repository,
        revision_repository=revision_repository,
    )

    assert state_repository.get(WORKFLOW_ID) == revision.state
    assert revision_repository.revisions() == (revision,)
    assert materialized_step(revision.state.specification).model_selection == PRIMARY


def test_promotion_keeps_substitutes_for_context_prompt_steps() -> None:
    specification = portfolio_workflow()

    substitution = WorkflowProductionModelSubstitution(
        step_id=STEP_ID,
        substitutes=(SUBSTITUTE,),
    )

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=create_candidate(specification),
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
        model_substitutions=(substitution,),
    )

    assert revision.state.model_substitutions == (substitution,)


def test_production_state_requires_fixed_models_for_context_prompt_steps() -> None:
    with pytest.raises(
        ValidationError,
        match="Production workflow prompt steps must use FixedModelSelection",
    ):
        WorkflowProductionState(
            specification=portfolio_workflow(),
        )


def test_production_state_accepts_substitutes_for_context_prompt_steps() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(context_specification(PRIMARY)),
        model_substitutions=(
            WorkflowProductionModelSubstitution(
                step_id=STEP_ID,
                substitutes=(SUBSTITUTE,),
            ),
        ),
    )

    assert state.model_substitutions[0].substitutes == (SUBSTITUTE,)


def test_production_state_rejects_a_context_prompt_primary_as_its_own_substitute() -> None:
    with pytest.raises(
        ValidationError,
        match="Production model substitutes cannot include the step's primary model",
    ):
        WorkflowProductionState(
            specification=create_workflow(context_specification(PRIMARY)),
            model_substitutions=(
                WorkflowProductionModelSubstitution(
                    step_id=STEP_ID,
                    substitutes=(PRIMARY,),
                ),
            ),
        )

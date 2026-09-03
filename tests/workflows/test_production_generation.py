"""Tests for generating executable production workflow candidates."""

from uuid import UUID

import pytest

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategy,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    ProductionModelSubstitutesUnavailableError,
    WorkflowMetadata,
    WorkflowProductionModelSubstitution,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    generate_production_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
FIRST_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")
SECOND_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="primary",
)

SUBSTITUTE = FixedModelSelection(
    provider="test-provider",
    model="substitute",
)

SECOND_PRIMARY = FixedModelSelection(
    provider="other-provider",
    model="second-primary",
)

UNAPPROVED = FixedModelSelection(
    provider="test-provider",
    model="unapproved",
)


def create_metadata(
    selection: FixedModelSelection,
) -> ModelMetadata:
    """Create deterministic metadata for one model."""

    return ModelMetadata(
        provider=selection.provider,
        model=selection.model,
        display_name=selection.identifier,
    )


def create_catalog(
    *selections: FixedModelSelection,
) -> ModelCatalog:
    """Create current model catalog."""

    return ModelCatalog(models=tuple(create_metadata(selection) for selection in selections))


def create_registry(
    *selections: FixedModelSelection,
) -> LanguageModelRegistry:
    """Create executable models for supplied selections."""

    return LanguageModelRegistry(
        {
            selection.identifier: DeterministicLanguageModel(
                provider=selection.provider,
                model=selection.model,
            )
            for selection in selections
        }
    )


def create_prompt_specification(
    *,
    strategy_id: UUID,
    name: str,
    selection: FixedModelSelection,
) -> PromptStrategySpec:
    """Create one deterministic fixed production prompt."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            id=strategy_id,
            name=name,
            description="Exercise production candidate generation.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text="Process the production request.",
        ),
        model_selection=selection,
    )


def create_production_state(
    *,
    substitutions: tuple[
        WorkflowProductionModelSubstitution,
        ...,
    ] = (),
) -> WorkflowProductionState:
    """Create deterministic multi-step production state."""

    specification = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="production-generation",
            description="Exercise production candidate generation.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=FIRST_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=FIRST_STRATEGY_ID,
                    name="first-step",
                    selection=PRIMARY,
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=SECOND_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=SECOND_STRATEGY_ID,
                    name="second-step",
                    selection=SECOND_PRIMARY,
                ),
                depends_on=(FIRST_STEP_ID,),
                outputs=(
                    WorkflowValueBinding(
                        name="confidence",
                    ),
                ),
            ),
        ),
    )

    return WorkflowProductionState(
        specification=specification,
        model_substitutions=substitutions,
    )


def test_production_generation_uses_available_primary_models() -> None:
    state = create_production_state()

    candidate = generate_production_workflow_candidate(
        state=state,
        catalog=create_catalog(
            PRIMARY,
            SECOND_PRIMARY,
        ),
        registry=create_registry(
            PRIMARY,
            SECOND_PRIMARY,
        ),
    )

    first = candidate.steps[0].strategy
    second = candidate.steps[1].strategy

    assert isinstance(
        first,
        PromptStrategy,
    )

    assert isinstance(
        second,
        PromptStrategy,
    )

    assert first.model_binding is not None
    assert second.model_binding is not None

    assert first.model_binding.identifier == PRIMARY.identifier
    assert second.model_binding.identifier == SECOND_PRIMARY.identifier


def test_production_generation_uses_approved_substitute() -> None:
    state = create_production_state(
        substitutions=(
            WorkflowProductionModelSubstitution(
                step_id=FIRST_STEP_ID,
                substitutes=(SUBSTITUTE,),
            ),
        ),
    )

    candidate = generate_production_workflow_candidate(
        state=state,
        catalog=create_catalog(
            SUBSTITUTE,
            SECOND_PRIMARY,
        ),
        registry=create_registry(
            SUBSTITUTE,
            SECOND_PRIMARY,
        ),
    )

    first = candidate.steps[0].strategy

    assert isinstance(
        first,
        PromptStrategy,
    )

    assert first.model_binding is not None

    assert first.model_binding.identifier == SUBSTITUTE.identifier


def test_production_generation_resolves_steps_independently() -> None:
    state = create_production_state(
        substitutions=(
            WorkflowProductionModelSubstitution(
                step_id=FIRST_STEP_ID,
                substitutes=(SUBSTITUTE,),
            ),
        ),
    )

    candidate = generate_production_workflow_candidate(
        state=state,
        catalog=create_catalog(
            SUBSTITUTE,
            SECOND_PRIMARY,
        ),
        registry=create_registry(
            SUBSTITUTE,
            SECOND_PRIMARY,
        ),
    )

    first = candidate.steps[0].strategy
    second = candidate.steps[1].strategy

    assert isinstance(
        first,
        PromptStrategy,
    )

    assert isinstance(
        second,
        PromptStrategy,
    )

    assert first.model_binding is not None
    assert second.model_binding is not None

    assert first.model_binding.identifier == SUBSTITUTE.identifier
    assert second.model_binding.identifier == SECOND_PRIMARY.identifier


def test_production_generation_preserves_workflow_identity() -> None:
    state = create_production_state()

    candidate = generate_production_workflow_candidate(
        state=state,
        catalog=create_catalog(
            PRIMARY,
            SECOND_PRIMARY,
        ),
        registry=create_registry(
            PRIMARY,
            SECOND_PRIMARY,
        ),
    )

    assert candidate.metadata == state.specification.metadata


def test_production_generation_preserves_step_identity_and_topology() -> None:
    state = create_production_state()

    candidate = generate_production_workflow_candidate(
        state=state,
        catalog=create_catalog(
            PRIMARY,
            SECOND_PRIMARY,
        ),
        registry=create_registry(
            PRIMARY,
            SECOND_PRIMARY,
        ),
    )

    assert tuple(step.id for step in candidate.steps) == (
        FIRST_STEP_ID,
        SECOND_STEP_ID,
    )

    assert candidate.steps[0].depends_on == ()
    assert candidate.steps[1].depends_on == (FIRST_STEP_ID,)


def test_production_generation_preserves_output_bindings() -> None:
    state = create_production_state()

    candidate = generate_production_workflow_candidate(
        state=state,
        catalog=create_catalog(
            PRIMARY,
            SECOND_PRIMARY,
        ),
        registry=create_registry(
            PRIMARY,
            SECOND_PRIMARY,
        ),
    )

    assert candidate.steps[0].outputs == (
        WorkflowValueBinding(
            name="classification",
        ),
    )

    assert candidate.steps[1].outputs == (
        WorkflowValueBinding(
            name="confidence",
        ),
    )


def test_production_generation_does_not_mutate_production_state() -> None:
    state = create_production_state(
        substitutions=(
            WorkflowProductionModelSubstitution(
                step_id=FIRST_STEP_ID,
                substitutes=(SUBSTITUTE,),
            ),
        ),
    )

    generate_production_workflow_candidate(
        state=state,
        catalog=create_catalog(
            SUBSTITUTE,
            SECOND_PRIMARY,
        ),
        registry=create_registry(
            SUBSTITUTE,
            SECOND_PRIMARY,
        ),
    )

    first_specification = state.specification.steps[0].specification

    assert isinstance(
        first_specification,
        PromptStrategySpec,
    )

    assert first_specification.model_selection == PRIMARY


def test_production_generation_does_not_use_unapproved_model() -> None:
    state = create_production_state(
        substitutions=(
            WorkflowProductionModelSubstitution(
                step_id=FIRST_STEP_ID,
                substitutes=(SUBSTITUTE,),
            ),
        ),
    )

    with pytest.raises(
        ProductionModelSubstitutesUnavailableError,
    ):
        generate_production_workflow_candidate(
            state=state,
            catalog=create_catalog(
                UNAPPROVED,
                SECOND_PRIMARY,
            ),
            registry=create_registry(
                UNAPPROVED,
                SECOND_PRIMARY,
            ),
        )

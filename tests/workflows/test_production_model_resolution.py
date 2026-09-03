"""Tests for explicit production model resolution."""

from uuid import UUID

import pytest

from azathoth.prompting import (
    FixedModelSelection,
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
    ProductionPrimaryModelUnavailableError,
    WorkflowMetadata,
    WorkflowProductionModelSubstitution,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    resolve_production_model_selection,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
TOOL_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="primary",
)

FIRST_SUBSTITUTE = FixedModelSelection(
    provider="test-provider",
    model="first-substitute",
)

SECOND_SUBSTITUTE = FixedModelSelection(
    provider="other-provider",
    model="second-substitute",
)


def create_metadata(
    selection: FixedModelSelection,
) -> ModelMetadata:
    """Create current model metadata for one fixed selection."""

    return ModelMetadata(
        provider=selection.provider,
        model=selection.model,
        display_name=selection.identifier,
    )


def create_registry(
    *selections: FixedModelSelection,
) -> LanguageModelRegistry:
    """Create executable models for supplied fixed selections."""

    return LanguageModelRegistry(
        {
            selection.identifier: DeterministicLanguageModel(
                provider=selection.provider,
                model=selection.model,
            )
            for selection in selections
        }
    )


def create_catalog(
    *selections: FixedModelSelection,
) -> ModelCatalog:
    """Create current model catalog containing supplied selections."""

    return ModelCatalog(models=tuple(create_metadata(selection) for selection in selections))


def create_production_state(
    *,
    substitutions: tuple[
        WorkflowProductionModelSubstitution,
        ...,
    ] = (),
) -> WorkflowProductionState:
    """Create deterministic production state."""

    specification = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="production-model-resolution",
            description="Exercise production model resolution.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="production-prompt",
                        description="Exercise production model resolution.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Process the production request.",
                    ),
                    model_selection=PRIMARY,
                ),
            ),
        ),
    )

    return WorkflowProductionState(
        specification=specification,
        model_substitutions=substitutions,
    )


def create_substitutions() -> tuple[
    WorkflowProductionModelSubstitution,
    ...,
]:
    """Create ordered approved substitutes for the production step."""

    return (
        WorkflowProductionModelSubstitution(
            step_id=STEP_ID,
            substitutes=(
                FIRST_SUBSTITUTE,
                SECOND_SUBSTITUTE,
            ),
        ),
    )


def test_production_resolution_uses_available_primary() -> None:
    state = create_production_state(
        substitutions=create_substitutions(),
    )

    selection = resolve_production_model_selection(
        state=state,
        step_id=STEP_ID,
        catalog=create_catalog(
            PRIMARY,
            FIRST_SUBSTITUTE,
            SECOND_SUBSTITUTE,
        ),
        registry=create_registry(
            PRIMARY,
            FIRST_SUBSTITUTE,
            SECOND_SUBSTITUTE,
        ),
    )

    assert selection == PRIMARY


def test_production_resolution_uses_first_approved_substitute() -> None:
    state = create_production_state(
        substitutions=create_substitutions(),
    )

    selection = resolve_production_model_selection(
        state=state,
        step_id=STEP_ID,
        catalog=create_catalog(
            FIRST_SUBSTITUTE,
            SECOND_SUBSTITUTE,
        ),
        registry=create_registry(
            FIRST_SUBSTITUTE,
            SECOND_SUBSTITUTE,
        ),
    )

    assert selection == FIRST_SUBSTITUTE


def test_production_resolution_preserves_substitute_order() -> None:
    state = create_production_state(
        substitutions=create_substitutions(),
    )

    selection = resolve_production_model_selection(
        state=state,
        step_id=STEP_ID,
        catalog=create_catalog(
            SECOND_SUBSTITUTE,
            FIRST_SUBSTITUTE,
        ),
        registry=create_registry(
            SECOND_SUBSTITUTE,
            FIRST_SUBSTITUTE,
        ),
    )

    assert selection == FIRST_SUBSTITUTE


def test_production_resolution_skips_unavailable_first_substitute() -> None:
    state = create_production_state(
        substitutions=create_substitutions(),
    )

    selection = resolve_production_model_selection(
        state=state,
        step_id=STEP_ID,
        catalog=create_catalog(
            SECOND_SUBSTITUTE,
        ),
        registry=create_registry(
            SECOND_SUBSTITUTE,
        ),
    )

    assert selection == SECOND_SUBSTITUTE


def test_production_resolution_requires_model_in_current_catalog() -> None:
    state = create_production_state(
        substitutions=create_substitutions(),
    )

    selection = resolve_production_model_selection(
        state=state,
        step_id=STEP_ID,
        catalog=create_catalog(
            FIRST_SUBSTITUTE,
        ),
        registry=create_registry(
            PRIMARY,
            FIRST_SUBSTITUTE,
        ),
    )

    assert selection == FIRST_SUBSTITUTE


def test_production_resolution_requires_executable_registry_model() -> None:
    state = create_production_state(
        substitutions=create_substitutions(),
    )

    selection = resolve_production_model_selection(
        state=state,
        step_id=STEP_ID,
        catalog=create_catalog(
            PRIMARY,
            FIRST_SUBSTITUTE,
        ),
        registry=create_registry(
            FIRST_SUBSTITUTE,
        ),
    )

    assert selection == FIRST_SUBSTITUTE


def test_production_resolution_rejects_unavailable_primary_without_substitutes() -> None:
    state = create_production_state()

    with pytest.raises(
        ProductionPrimaryModelUnavailableError,
        match="Production primary model",
    ):
        resolve_production_model_selection(
            state=state,
            step_id=STEP_ID,
            catalog=ModelCatalog(),
            registry=LanguageModelRegistry(),
        )


def test_production_resolution_rejects_exhausted_approved_substitutes() -> None:
    state = create_production_state(
        substitutions=create_substitutions(),
    )

    with pytest.raises(
        ProductionModelSubstitutesUnavailableError,
        match="No approved production model substitute is available",
    ):
        resolve_production_model_selection(
            state=state,
            step_id=STEP_ID,
            catalog=ModelCatalog(),
            registry=LanguageModelRegistry(),
        )


def test_production_resolution_does_not_use_unapproved_available_model() -> None:
    state = create_production_state(
        substitutions=create_substitutions(),
    )

    unapproved = FixedModelSelection(
        provider="test-provider",
        model="unapproved-model",
    )

    with pytest.raises(
        ProductionModelSubstitutesUnavailableError,
    ):
        resolve_production_model_selection(
            state=state,
            step_id=STEP_ID,
            catalog=create_catalog(
                unapproved,
            ),
            registry=create_registry(
                unapproved,
            ),
        )


def test_production_resolution_rejects_unknown_workflow_step() -> None:
    unknown_step_id = UUID("55555555-5555-5555-5555-555555555555")

    state = create_production_state()

    with pytest.raises(
        ValueError,
        match=(f"Workflow step {unknown_step_id} does not exist in production state"),
    ):
        resolve_production_model_selection(
            state=state,
            step_id=unknown_step_id,
            catalog=create_catalog(
                PRIMARY,
            ),
            registry=create_registry(
                PRIMARY,
            ),
        )

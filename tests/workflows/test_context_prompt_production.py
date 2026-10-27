"""Tests for executing production workflows whose prompt steps render from context."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    FixedModelSelection,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    ProductionInvocationSuccess,
    ProductionModelSubstitutesUnavailableError,
    ProductionPrimaryModelUnavailableError,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowRunRepository,
    WorkflowMetadata,
    WorkflowProductionEmission,
    WorkflowProductionModelSubstitution,
    WorkflowProductionState,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
    complete_production_invocation,
    create_production_invocation,
    generate_production_workflow_candidate,
    resolve_production_model_selection,
)

WORKFLOW_ID = UUID("72000000-0000-4000-8000-000000000001")

STEP_ID = UUID("72000000-0000-4000-8000-000000000002")

STRATEGY_ID = UUID("72000000-0000-4000-8000-000000000003")

PRIMARY = FixedModelSelection(provider="test", model="primary")

SUBSTITUTE = FixedModelSelection(provider="test", model="substitute")


def create_state(
    *,
    substitutes: tuple[FixedModelSelection, ...] = (SUBSTITUTE,),
) -> WorkflowProductionState:
    """Create production state with one context-prompt step bound to the input."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="context production",
                description="Classify the production input.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=ContextPromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="classify input",
                            description="Classify the production input.",
                            version="1.0.0",
                        ),
                        template=PromptTemplate(
                            text="Classify: {text}",
                            bindings=(
                                PromptBinding(
                                    variable_name="text",
                                    event_type=WORKFLOW_INPUT_EVENT_TYPE,
                                    field_name="input",
                                ),
                            ),
                        ),
                        model_selection=PRIMARY,
                    ),
                    outputs=(WorkflowValueBinding(name="label"),),
                ),
            ),
            result=WorkflowValueReference(
                producer_step_id=STEP_ID,
                name="label",
            ),
        ),
        model_substitutions=(
            (
                WorkflowProductionModelSubstitution(
                    step_id=STEP_ID,
                    substitutes=substitutes,
                ),
            )
            if substitutes
            else ()
        ),
        emissions=(
            WorkflowProductionEmission(
                name="result",
                source=WorkflowValueReference(
                    producer_step_id=STEP_ID,
                    name="label",
                ),
            ),
        ),
    )


def current(
    *selections: FixedModelSelection,
) -> tuple[ModelCatalog, LanguageModelRegistry]:
    """Return a catalog and registry in which only these models are executable."""

    catalog = ModelCatalog(
        models=tuple(
            ModelMetadata(
                provider=selection.provider,
                model=selection.model,
                display_name=selection.identifier,
            )
            for selection in selections
        )
    )

    registry = LanguageModelRegistry(
        {
            selection.identifier: DeterministicLanguageModel(
                provider=selection.provider,
                model=selection.model,
                response_text=f"answered by {selection.model}",
            )
            for selection in selections
        }
    )

    return catalog, registry


def test_resolution_keeps_an_executable_context_prompt_primary() -> None:
    catalog, registry = current(PRIMARY, SUBSTITUTE)

    assert (
        resolve_production_model_selection(
            state=create_state(),
            step_id=STEP_ID,
            catalog=catalog,
            registry=registry,
        )
        == PRIMARY
    )


def test_resolution_falls_back_to_an_approved_context_prompt_substitute() -> None:
    catalog, registry = current(SUBSTITUTE)

    assert (
        resolve_production_model_selection(
            state=create_state(),
            step_id=STEP_ID,
            catalog=catalog,
            registry=registry,
        )
        == SUBSTITUTE
    )


def test_resolution_reports_an_unavailable_context_prompt_primary_without_substitutes() -> None:
    catalog, registry = current()

    with pytest.raises(ProductionPrimaryModelUnavailableError):
        resolve_production_model_selection(
            state=create_state(substitutes=()),
            step_id=STEP_ID,
            catalog=catalog,
            registry=registry,
        )


def test_resolution_reports_unavailable_context_prompt_substitutes() -> None:
    catalog, registry = current()

    with pytest.raises(ProductionModelSubstitutesUnavailableError):
        resolve_production_model_selection(
            state=create_state(),
            step_id=STEP_ID,
            catalog=catalog,
            registry=registry,
        )


def test_production_candidate_binds_a_context_prompt_step_to_its_substitute() -> None:
    catalog, registry = current(SUBSTITUTE)

    candidate = generate_production_workflow_candidate(
        state=create_state(),
        catalog=catalog,
        registry=registry,
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(strategy, ContextPromptStrategy)
    assert strategy.model_binding is not None
    assert strategy.model_binding.identifier == SUBSTITUTE.identifier


def test_production_invocation_runs_a_context_prompt_step_on_its_substitute(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"
    catalog, registry = current(SUBSTITUTE)
    invocation_repository = SQLiteProductionInvocationRepository(database)

    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload="The checkout flow was painless.",
    )

    invocation_repository.save(invocation)

    result = asyncio.run(
        complete_production_invocation(
            invocation=invocation,
            state=create_state(),
            catalog=catalog,
            registry=registry,
            runner=WorkflowRunner(),
            run_repository=SQLiteWorkflowRunRepository(database),
            invocation_repository=invocation_repository,
            invocation_run_repository=SQLiteProductionInvocationRunRepository(database),
        )
    )

    assert isinstance(result, ProductionInvocationSuccess)
    assert result.result == {"result": "answered by substitute"}

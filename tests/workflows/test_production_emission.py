"""Tests for explicit workflow production emissions."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowProductionEmission,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
FIRST_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
SECOND_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST_STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")
SECOND_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")


def create_prompt_specification(
    *,
    strategy_id: UUID,
    name: str,
) -> PromptStrategySpec:
    """Create one deterministic production prompt specification."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            id=strategy_id,
            name=name,
            description="Exercise production emissions.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text="Process the request.",
        ),
        model_selection=FixedModelSelection(
            provider="test-provider",
            model="production-model",
        ),
    )


def create_workflow() -> WorkflowSpecification:
    """Create a workflow with intentional exported values."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="production-emission-workflow",
            description="Exercise explicit production emissions.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=FIRST_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=FIRST_STRATEGY_ID,
                    name="classify",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                    ),
                    WorkflowValueBinding(
                        name="internal_analysis",
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=SECOND_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=SECOND_STRATEGY_ID,
                    name="score-confidence",
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


def test_production_state_defaults_to_no_public_emissions() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(),
    )

    assert state.emissions == ()


def test_production_state_preserves_explicit_emission() -> None:
    emission = WorkflowProductionEmission(
        name="label",
        source=WorkflowValueReference(
            producer_step_id=FIRST_STEP_ID,
            name="classification",
        ),
    )

    state = WorkflowProductionState(
        specification=create_workflow(),
        emissions=(emission,),
    )

    assert state.emissions == (emission,)


def test_production_emission_can_rename_internal_workflow_value() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(),
        emissions=(
            WorkflowProductionEmission(
                name="label",
                source=WorkflowValueReference(
                    producer_step_id=FIRST_STEP_ID,
                    name="classification",
                ),
            ),
        ),
    )

    emission = state.emissions[0]

    assert emission.name == "label"
    assert emission.source.name == "classification"


def test_production_emissions_preserve_declared_order() -> None:
    first = WorkflowProductionEmission(
        name="label",
        source=WorkflowValueReference(
            producer_step_id=FIRST_STEP_ID,
            name="classification",
        ),
    )

    second = WorkflowProductionEmission(
        name="confidence",
        source=WorkflowValueReference(
            producer_step_id=SECOND_STEP_ID,
            name="confidence",
        ),
    )

    state = WorkflowProductionState(
        specification=create_workflow(),
        emissions=(
            first,
            second,
        ),
    )

    assert state.emissions == (
        first,
        second,
    )


def test_production_state_rejects_duplicate_emission_names() -> None:
    with pytest.raises(
        ValidationError,
        match="Production emission names must be unique",
    ):
        WorkflowProductionState(
            specification=create_workflow(),
            emissions=(
                WorkflowProductionEmission(
                    name="result",
                    source=WorkflowValueReference(
                        producer_step_id=FIRST_STEP_ID,
                        name="classification",
                    ),
                ),
                WorkflowProductionEmission(
                    name="result",
                    source=WorkflowValueReference(
                        producer_step_id=SECOND_STEP_ID,
                        name="confidence",
                    ),
                ),
            ),
        )


def test_production_state_rejects_emission_from_unknown_step() -> None:
    unknown_step_id = UUID("66666666-6666-6666-6666-666666666666")

    with pytest.raises(
        ValidationError,
        match=("Production emissions must reference workflow steps"),
    ):
        WorkflowProductionState(
            specification=create_workflow(),
            emissions=(
                WorkflowProductionEmission(
                    name="result",
                    source=WorkflowValueReference(
                        producer_step_id=unknown_step_id,
                        name="classification",
                    ),
                ),
            ),
        )


def test_production_state_rejects_undeclared_emission_value() -> None:
    with pytest.raises(
        ValidationError,
        match=("Production emissions must reference declared workflow outputs"),
    ):
        WorkflowProductionState(
            specification=create_workflow(),
            emissions=(
                WorkflowProductionEmission(
                    name="secret",
                    source=WorkflowValueReference(
                        producer_step_id=FIRST_STEP_ID,
                        name="not-declared",
                    ),
                ),
            ),
        )


def test_production_emission_is_immutable() -> None:
    emission = WorkflowProductionEmission(
        name="label",
        source=WorkflowValueReference(
            producer_step_id=FIRST_STEP_ID,
            name="classification",
        ),
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        emission.__setattr__(
            "name",
            "changed",
        )

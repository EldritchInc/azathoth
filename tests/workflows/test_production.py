"""Tests for durable workflow production state."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    FixedModelSelection,
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_workflow(
    *,
    fixed: bool = False,
) -> WorkflowSpecification:
    """Create one deterministic durable workflow specification."""

    model_selection = (
        FixedModelSelection(
            provider="test-provider",
            model="production-model",
        )
        if fixed
        else PortfolioModelSelection(
            requirements=ModelRequirements(),
        )
    )

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="production-workflow",
            description="Exercise durable production state.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="production-prompt",
                        description="Exercise production workflow state.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=model_selection,
                ),
            ),
        ),
    )


def test_production_state_records_workflow_specification() -> None:
    specification = create_workflow()

    state = WorkflowProductionState(
        specification=specification,
    )

    assert state.specification is specification


def test_production_state_preserves_workflow_identity() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(),
    )

    assert state.specification.metadata.id == WORKFLOW_ID


def test_production_state_accepts_fixed_model_selection() -> None:
    specification = create_workflow(
        fixed=True,
    )

    state = WorkflowProductionState(
        specification=specification,
    )

    prompt = state.specification.steps[0].specification

    assert isinstance(
        prompt,
        PromptStrategySpec,
    )

    assert isinstance(
        prompt.model_selection,
        FixedModelSelection,
    )

    assert prompt.model_selection.identifier == ("test-provider/production-model")


def test_production_state_does_not_require_fixed_model_selection() -> None:
    specification = create_workflow()

    state = WorkflowProductionState(
        specification=specification,
    )

    prompt = state.specification.steps[0].specification

    assert isinstance(
        prompt,
        PromptStrategySpec,
    )

    assert isinstance(
        prompt.model_selection,
        PortfolioModelSelection,
    )


def test_production_state_is_immutable() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(),
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        state.specification = create_workflow(
            fixed=True,
        )


def test_production_state_round_trips_through_json() -> None:
    state = WorkflowProductionState(
        specification=create_workflow(
            fixed=True,
        ),
    )

    restored = WorkflowProductionState.model_validate_json(
        state.model_dump_json(),
    )

    assert restored == state

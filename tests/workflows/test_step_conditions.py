"""Tests for conditions attached to workflow steps."""

from uuid import UUID

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCondition,
    WorkflowStepSpecification,
    WorkflowValueReference,
)

STEP_ID = UUID("37000993-654a-4dad-adb3-f60c522d1593")
PRODUCER_STEP_ID = UUID("ead5db76-28cf-426b-88fc-f06c06048650")
STRATEGY_ID = UUID("d904a7ae-e12e-4b19-af59-519e88644193")


def create_prompt_specification() -> PromptStrategySpec:
    """Create a deterministic prompt specification."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            id=STRATEGY_ID,
            name="Conditional reasoner",
            description="Execute a conditionally eligible workflow step.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text="Reason about the request.",
        ),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(),
        ),
    )


def create_condition() -> WorkflowCondition:
    """Create a deterministic workflow condition."""

    return WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=PRODUCER_STEP_ID,
            name="classification",
        ),
        expected="math",
    )


def test_workflow_step_defaults_to_no_conditions() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
    )

    assert step.conditions == ()


def test_workflow_step_records_conditions() -> None:
    condition = create_condition()

    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
        depends_on=(PRODUCER_STEP_ID,),
        conditions=(condition,),
    )

    assert step.conditions == (condition,)


def test_workflow_step_preserves_condition_order() -> None:
    classification_condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=PRODUCER_STEP_ID,
            name="classification",
        ),
        expected="math",
    )
    confidence_condition = WorkflowCondition(
        source=WorkflowValueReference(
            producer_step_id=PRODUCER_STEP_ID,
            name="confidence",
        ),
        expected=0.95,
    )

    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
        depends_on=(PRODUCER_STEP_ID,),
        conditions=(
            classification_condition,
            confidence_condition,
        ),
    )

    assert step.conditions == (
        classification_condition,
        confidence_condition,
    )


def test_workflow_step_conditions_round_trip_through_json() -> None:
    step = WorkflowStepSpecification(
        id=STEP_ID,
        specification=create_prompt_specification(),
        depends_on=(PRODUCER_STEP_ID,),
        conditions=(create_condition(),),
    )

    restored = WorkflowStepSpecification.model_validate_json(step.model_dump_json())

    assert restored == step
    assert restored.conditions == step.conditions

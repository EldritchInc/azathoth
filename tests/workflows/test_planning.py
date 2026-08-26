"""Tests for deterministic workflow execution planning."""

from uuid import UUID

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

STEP_A_ID = UUID("e445a23b-f66c-4498-8224-eed45aa98b23")
STEP_B_ID = UUID("73ed36d8-d27d-44c7-a04d-3945d549dc43")
STEP_C_ID = UUID("61e4c807-259e-487a-bf58-b188db795482")
STEP_D_ID = UUID("1346cc9b-3c1b-408d-a8b6-1c79864c2d27")


def create_step(
    *,
    step_id: UUID,
    name: str,
    depends_on: tuple[UUID, ...] = (),
) -> WorkflowStepSpecification:
    """Create a deterministic workflow step."""

    return WorkflowStepSpecification(
        id=step_id,
        depends_on=depends_on,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                name=name,
                description=f"Execute the {name} step.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text=f"Execute {name}.",
            ),
            model_selection=PortfolioModelSelection(
                requirements=ModelRequirements(),
            ),
        ),
    )


def create_workflow(
    *steps: WorkflowStepSpecification,
) -> WorkflowSpecification:
    """Create a deterministic workflow containing supplied steps."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Execution planning workflow",
            description="A workflow used to test dependency planning.",
            version="1.0.0",
        ),
        steps=steps,
    )


def test_execution_layers_for_linear_workflow() -> None:
    step_a = create_step(
        step_id=STEP_A_ID,
        name="A",
    )
    step_b = create_step(
        step_id=STEP_B_ID,
        name="B",
        depends_on=(STEP_A_ID,),
    )
    step_c = create_step(
        step_id=STEP_C_ID,
        name="C",
        depends_on=(STEP_B_ID,),
    )

    workflow = create_workflow(
        step_a,
        step_b,
        step_c,
    )

    layers = workflow.execution_layers()

    assert tuple(tuple(step.id for step in layer) for layer in layers) == (
        (STEP_A_ID,),
        (STEP_B_ID,),
        (STEP_C_ID,),
    )


def test_independent_root_steps_share_first_execution_layer() -> None:
    step_a = create_step(
        step_id=STEP_A_ID,
        name="A",
    )
    step_b = create_step(
        step_id=STEP_B_ID,
        name="B",
    )
    step_c = create_step(
        step_id=STEP_C_ID,
        name="C",
        depends_on=(
            STEP_A_ID,
            STEP_B_ID,
        ),
    )

    workflow = create_workflow(
        step_a,
        step_b,
        step_c,
    )

    layers = workflow.execution_layers()

    assert tuple(tuple(step.id for step in layer) for layer in layers) == (
        (
            STEP_A_ID,
            STEP_B_ID,
        ),
        (STEP_C_ID,),
    )


def test_execution_layers_for_diamond_workflow() -> None:
    step_a = create_step(
        step_id=STEP_A_ID,
        name="A",
    )
    step_b = create_step(
        step_id=STEP_B_ID,
        name="B",
        depends_on=(STEP_A_ID,),
    )
    step_c = create_step(
        step_id=STEP_C_ID,
        name="C",
        depends_on=(STEP_A_ID,),
    )
    step_d = create_step(
        step_id=STEP_D_ID,
        name="D",
        depends_on=(
            STEP_B_ID,
            STEP_C_ID,
        ),
    )

    workflow = create_workflow(
        step_a,
        step_b,
        step_c,
        step_d,
    )

    layers = workflow.execution_layers()

    assert tuple(tuple(step.id for step in layer) for layer in layers) == (
        (STEP_A_ID,),
        (
            STEP_B_ID,
            STEP_C_ID,
        ),
        (STEP_D_ID,),
    )


def test_execution_layers_preserve_declared_order() -> None:
    step_b = create_step(
        step_id=STEP_B_ID,
        name="B",
    )
    step_a = create_step(
        step_id=STEP_A_ID,
        name="A",
    )
    step_c = create_step(
        step_id=STEP_C_ID,
        name="C",
        depends_on=(
            STEP_A_ID,
            STEP_B_ID,
        ),
    )

    workflow = create_workflow(
        step_b,
        step_a,
        step_c,
    )

    layers = workflow.execution_layers()

    assert tuple(step.id for step in layers[0]) == (
        STEP_B_ID,
        STEP_A_ID,
    )


def test_execution_planning_does_not_mutate_workflow() -> None:
    step_a = create_step(
        step_id=STEP_A_ID,
        name="A",
    )
    step_b = create_step(
        step_id=STEP_B_ID,
        name="B",
        depends_on=(STEP_A_ID,),
    )
    workflow = create_workflow(
        step_a,
        step_b,
    )
    original_steps = workflow.steps

    workflow.execution_layers()

    assert workflow.steps == original_steps


def test_single_step_workflow_has_one_execution_layer() -> None:
    step = create_step(
        step_id=STEP_A_ID,
        name="A",
    )

    workflow = create_workflow(step)

    assert workflow.execution_layers() == ((step,),)

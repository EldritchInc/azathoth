"""Tests for workflow value reference validation."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)

STEP_A_ID = UUID("203802d9-91fa-42df-88fd-bc780154d120")
STEP_B_ID = UUID("077f17df-2291-46c3-b669-5719a02c29c4")
STEP_C_ID = UUID("5a462a26-8cfb-4daa-a011-492de18574ef")
STEP_D_ID = UUID("816ec040-8fc7-46ba-adde-6ea35c569a20")
UNKNOWN_STEP_ID = UUID("81a66ebe-c6f6-4cd7-aee1-93842864f1c3")


def create_step(
    *,
    step_id: UUID,
    name: str,
    depends_on: tuple[UUID, ...] = (),
    inputs: tuple[WorkflowInputBinding, ...] = (),
    outputs: tuple[WorkflowValueBinding, ...] = (),
) -> WorkflowStepSpecification:
    """Create a deterministic workflow step."""

    return WorkflowStepSpecification(
        id=step_id,
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
        depends_on=depends_on,
        inputs=inputs,
        outputs=outputs,
    )


def create_workflow(
    *steps: WorkflowStepSpecification,
) -> WorkflowSpecification:
    """Create a deterministic workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Workflow value validation",
            description="Validate workflow value dataflow.",
            version="1.0.0",
        ),
        steps=steps,
    )


def test_direct_upstream_value_reference_is_valid() -> None:
    producer = create_step(
        step_id=STEP_A_ID,
        name="Producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    consumer = create_step(
        step_id=STEP_B_ID,
        name="Consumer",
        depends_on=(STEP_A_ID,),
        inputs=(
            WorkflowInputBinding(
                name="classification",
                source=WorkflowValueReference(
                    producer_step_id=STEP_A_ID,
                    name="classification",
                ),
            ),
        ),
    )

    workflow = create_workflow(
        producer,
        consumer,
    )

    assert workflow.steps == (
        producer,
        consumer,
    )


def test_transitive_upstream_value_reference_is_valid() -> None:
    producer = create_step(
        step_id=STEP_A_ID,
        name="Producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    middle = create_step(
        step_id=STEP_B_ID,
        name="Middle",
        depends_on=(STEP_A_ID,),
    )
    consumer = create_step(
        step_id=STEP_C_ID,
        name="Consumer",
        depends_on=(STEP_B_ID,),
        inputs=(
            WorkflowInputBinding(
                name="classification",
                source=WorkflowValueReference(
                    producer_step_id=STEP_A_ID,
                    name="classification",
                ),
            ),
        ),
    )

    workflow = create_workflow(
        producer,
        middle,
        consumer,
    )

    assert workflow.steps[2] == consumer


def test_unknown_value_producer_is_rejected() -> None:
    consumer = create_step(
        step_id=STEP_A_ID,
        name="Consumer",
        inputs=(
            WorkflowInputBinding(
                name="classification",
                source=WorkflowValueReference(
                    producer_step_id=UNKNOWN_STEP_ID,
                    name="classification",
                ),
            ),
        ),
    )

    with pytest.raises(
        ValidationError,
        match="producer step in the same workflow",
    ):
        create_workflow(consumer)


def test_reference_to_undeclared_output_is_rejected() -> None:
    producer = create_step(
        step_id=STEP_A_ID,
        name="Producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    consumer = create_step(
        step_id=STEP_B_ID,
        name="Consumer",
        depends_on=(STEP_A_ID,),
        inputs=(
            WorkflowInputBinding(
                name="confidence",
                source=WorkflowValueReference(
                    producer_step_id=STEP_A_ID,
                    name="confidence",
                ),
            ),
        ),
    )

    with pytest.raises(
        ValidationError,
        match="output declared by the producer step",
    ):
        create_workflow(
            producer,
            consumer,
        )


def test_same_layer_value_reference_is_rejected() -> None:
    producer = create_step(
        step_id=STEP_A_ID,
        name="Producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    consumer = create_step(
        step_id=STEP_B_ID,
        name="Consumer",
        inputs=(
            WorkflowInputBinding(
                name="classification",
                source=WorkflowValueReference(
                    producer_step_id=STEP_A_ID,
                    name="classification",
                ),
            ),
        ),
    )

    with pytest.raises(
        ValidationError,
        match="upstream workflow steps",
    ):
        create_workflow(
            producer,
            consumer,
        )


def test_downstream_value_reference_is_rejected() -> None:
    consumer = create_step(
        step_id=STEP_A_ID,
        name="Consumer",
        inputs=(
            WorkflowInputBinding(
                name="result",
                source=WorkflowValueReference(
                    producer_step_id=STEP_C_ID,
                    name="result",
                ),
            ),
        ),
    )
    middle = create_step(
        step_id=STEP_B_ID,
        name="Middle",
        depends_on=(STEP_A_ID,),
    )
    producer = create_step(
        step_id=STEP_C_ID,
        name="Producer",
        depends_on=(STEP_B_ID,),
        outputs=(
            WorkflowValueBinding(
                name="result",
            ),
        ),
    )

    with pytest.raises(
        ValidationError,
        match="upstream workflow steps",
    ):
        create_workflow(
            consumer,
            middle,
            producer,
        )


def test_duplicate_output_names_on_same_step_are_rejected() -> None:
    producer = create_step(
        step_id=STEP_A_ID,
        name="Producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )

    with pytest.raises(
        ValidationError,
        match="output names must be unique",
    ):
        create_workflow(producer)


def test_same_output_name_on_different_steps_is_valid() -> None:
    first = create_step(
        step_id=STEP_A_ID,
        name="First producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    second = create_step(
        step_id=STEP_B_ID,
        name="Second producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )

    workflow = create_workflow(
        first,
        second,
    )

    assert workflow.steps == (
        first,
        second,
    )


def test_duplicate_consumer_input_names_are_rejected() -> None:
    first_producer = create_step(
        step_id=STEP_A_ID,
        name="First producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    second_producer = create_step(
        step_id=STEP_B_ID,
        name="Second producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    consumer = create_step(
        step_id=STEP_C_ID,
        name="Consumer",
        depends_on=(
            STEP_A_ID,
            STEP_B_ID,
        ),
        inputs=(
            WorkflowInputBinding(
                name="route",
                source=WorkflowValueReference(
                    producer_step_id=STEP_A_ID,
                    name="classification",
                ),
            ),
            WorkflowInputBinding(
                name="route",
                source=WorkflowValueReference(
                    producer_step_id=STEP_B_ID,
                    name="classification",
                ),
            ),
        ),
    )

    with pytest.raises(
        ValidationError,
        match="input names must be unique",
    ):
        create_workflow(
            first_producer,
            second_producer,
            consumer,
        )


def test_distinct_input_aliases_are_valid() -> None:
    first_producer = create_step(
        step_id=STEP_A_ID,
        name="First producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    second_producer = create_step(
        step_id=STEP_B_ID,
        name="Second producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    consumer = create_step(
        step_id=STEP_C_ID,
        name="Consumer",
        depends_on=(
            STEP_A_ID,
            STEP_B_ID,
        ),
        inputs=(
            WorkflowInputBinding(
                name="first_route",
                source=WorkflowValueReference(
                    producer_step_id=STEP_A_ID,
                    name="classification",
                ),
            ),
            WorkflowInputBinding(
                name="second_route",
                source=WorkflowValueReference(
                    producer_step_id=STEP_B_ID,
                    name="classification",
                ),
            ),
        ),
    )

    workflow = create_workflow(
        first_producer,
        second_producer,
        consumer,
    )

    assert tuple(binding.name for binding in workflow.steps[2].inputs) == (
        "first_route",
        "second_route",
    )


def test_transitive_reference_is_valid_across_diamond_graph() -> None:
    producer = create_step(
        step_id=STEP_A_ID,
        name="Producer",
        outputs=(
            WorkflowValueBinding(
                name="classification",
            ),
        ),
    )
    left = create_step(
        step_id=STEP_B_ID,
        name="Left",
        depends_on=(STEP_A_ID,),
    )
    right = create_step(
        step_id=STEP_C_ID,
        name="Right",
        depends_on=(STEP_A_ID,),
    )
    consumer = create_step(
        step_id=STEP_D_ID,
        name="Consumer",
        depends_on=(
            STEP_B_ID,
            STEP_C_ID,
        ),
        inputs=(
            WorkflowInputBinding(
                name="classification",
                source=WorkflowValueReference(
                    producer_step_id=STEP_A_ID,
                    name="classification",
                ),
            ),
        ),
    )

    workflow = create_workflow(
        producer,
        left,
        right,
        consumer,
    )

    assert workflow.steps[3] == consumer

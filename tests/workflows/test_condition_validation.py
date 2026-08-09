"""Tests for validating workflow conditions."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import PromptStrategySpec
from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCondition,
    # WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("c59a2db0-fd7d-4e1f-b08b-43b665abdf2c")

STEP_ONE_ID = UUID("0a7f9ff7-9d92-42fd-8d55-962f5d4baf0b")
STEP_TWO_ID = UUID("95d4cb1e-7206-49a8-a24f-30d8d33d1f77")
STEP_THREE_ID = UUID("efbcf4f5-8264-4f1f-8c75-0d0c9c7e3ef8")


def create_prompt(name: str) -> PromptStrategySpec:
    """Create a deterministic prompt specification."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            name=name,
            description=name,
        ),
        prompt=Prompt(
            text=name,
        ),
        model_requirements=ModelRequirements(),
    )


def create_workflow() -> WorkflowSpecification:
    """Create a valid workflow containing a condition."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Conditional workflow",
            description="Workflow condition validation.",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ONE_ID,
                specification=create_prompt("Classifier"),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                        path=("classification",),
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=STEP_TWO_ID,
                specification=create_prompt("Reasoner"),
                depends_on=(STEP_ONE_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=STEP_ONE_ID,
                            name="classification",
                        ),
                        expected="math",
                    ),
                ),
            ),
        ),
    )


def test_reference_to_existing_upstream_output_is_valid() -> None:
    create_workflow()


def test_reference_to_unknown_step_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpecification(
            metadata=create_workflow().metadata,
            steps=(
                create_workflow().steps[0],
                create_workflow()
                .steps[1]
                .model_copy(
                    update={
                        "conditions": (
                            WorkflowCondition(
                                source=WorkflowValueReference(
                                    producer_step_id=STEP_THREE_ID,
                                    name="classification",
                                ),
                                expected="math",
                            ),
                        ),
                    }
                ),
            ),
        )


def test_reference_to_missing_output_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpecification(
            metadata=create_workflow().metadata,
            steps=(
                create_workflow().steps[0],
                create_workflow()
                .steps[1]
                .model_copy(
                    update={
                        "conditions": (
                            WorkflowCondition(
                                source=WorkflowValueReference(
                                    producer_step_id=STEP_ONE_ID,
                                    name="confidence",
                                ),
                                expected=0.9,
                            ),
                        ),
                    }
                ),
            ),
        )


def test_same_layer_condition_reference_is_rejected() -> None:
    workflow = create_workflow()

    with pytest.raises(ValidationError):
        WorkflowSpecification(
            metadata=workflow.metadata,
            steps=(
                workflow.steps[0],
                workflow.steps[1].model_copy(
                    update={
                        "depends_on": (),
                    }
                ),
            ),
        )


def test_transitive_condition_reference_is_valid() -> None:
    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Diamond",
            description="Diamond dependency graph.",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ONE_ID,
                specification=create_prompt("Classifier"),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                        path=("classification",),
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=STEP_TWO_ID,
                specification=create_prompt("Branch"),
                depends_on=(STEP_ONE_ID,),
            ),
            WorkflowStepSpecification(
                id=STEP_THREE_ID,
                specification=create_prompt("Reasoner"),
                depends_on=(STEP_TWO_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=STEP_ONE_ID,
                            name="classification",
                        ),
                        expected="math",
                    ),
                ),
            ),
        ),
    )

    assert workflow.steps[2].conditions[0].expected == "math"

"""Tests for durable workflow specification models."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import PromptStrategySpec
from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("a71a5bfb-e2cc-48d5-a055-985cc6450e48")
STEP_ONE_ID = UUID("7f8cc955-8cbf-407e-a902-7d8c8465696b")
STEP_TWO_ID = UUID("aa2ff5c7-ac35-44e2-af83-caf0b88b95c1")
STEP_THREE_ID = UUID("7f496d81-759b-45a3-91cb-f412abf17613")


def create_step(
    *,
    step_id: UUID,
    name: str,
) -> WorkflowStepSpecification:
    """Create a deterministic prompt-backed workflow step."""

    return WorkflowStepSpecification(
        id=step_id,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                name=name,
                description=f"{name} description.",
            ),
            prompt=Prompt(
                text=f"{name} prompt.",
            ),
            model_requirements=ModelRequirements(),
        ),
    )


def create_workflow() -> WorkflowSpecification:
    """Create a deterministic workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Support request workflow",
            description=(
                "Classify a request, determine whether tools are needed, and produce a response."
            ),
            version="1.0.0",
        ),
        steps=(
            create_step(
                step_id=STEP_ONE_ID,
                name="Classification",
            ),
            create_step(
                step_id=STEP_TWO_ID,
                name="Response",
            ),
            create_step(
                step_id=STEP_THREE_ID,
                name="Safety check",
            ),
        ),
    )


def test_workflow_specification_records_metadata_and_steps() -> None:
    workflow = create_workflow()

    assert workflow.metadata.id == WORKFLOW_ID
    assert workflow.metadata.name == "Support request workflow"
    assert tuple(step.id for step in workflow.steps) == (
        STEP_ONE_ID,
        STEP_TWO_ID,
        STEP_THREE_ID,
    )


def test_workflow_specification_preserves_step_order() -> None:
    workflow = create_workflow()

    assert tuple(step.specification.metadata.name for step in workflow.steps) == (
        "Classification",
        "Response",
        "Safety check",
    )


def test_workflow_metadata_defaults_version() -> None:
    metadata = WorkflowMetadata(
        name="Simple workflow",
        description="A simple workflow used by a test.",
    )

    assert metadata.version == "1.0.0"


def test_workflow_metadata_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowMetadata(
            name="",
            description="Valid description.",
        )


def test_workflow_metadata_rejects_empty_description() -> None:
    with pytest.raises(ValidationError):
        WorkflowMetadata(
            name="Valid name",
            description="",
        )


def test_workflow_specification_is_immutable() -> None:
    workflow = create_workflow()

    with pytest.raises(ValidationError):
        workflow.steps = ()


def test_workflow_metadata_is_immutable() -> None:
    metadata = create_workflow().metadata

    with pytest.raises(ValidationError):
        metadata.version = "2.0.0"


def test_workflow_specification_round_trips_through_json() -> None:
    workflow = create_workflow()

    restored = WorkflowSpecification.model_validate_json(workflow.model_dump_json())

    assert restored == workflow


def test_workflow_specification_can_be_created_before_steps_are_defined() -> None:
    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            name="Draft workflow",
            description="A workflow whose steps have not yet been defined.",
        ),
        steps=(),
    )

    assert workflow.steps == ()

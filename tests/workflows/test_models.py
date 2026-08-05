"""Tests for durable workflow specification models."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowSpecification,
)

WORKFLOW_ID = UUID("a71a5bfb-e2cc-48d5-a055-985cc6450e48")
STEP_ONE_ID = UUID("7f8cc955-8cbf-407e-a902-7d8c8465696b")
STEP_TWO_ID = UUID("aa2ff5c7-ac35-44e2-af83-caf0b88b95c1")
STEP_THREE_ID = UUID("7f496d81-759b-45a3-91cb-f412abf17613")


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
        step_ids=(
            STEP_ONE_ID,
            STEP_TWO_ID,
            STEP_THREE_ID,
        ),
    )


def test_workflow_specification_records_metadata_and_step_order() -> None:
    workflow = create_workflow()

    assert workflow.metadata.id == WORKFLOW_ID
    assert workflow.metadata.name == "Support request workflow"
    assert workflow.step_ids == (
        STEP_ONE_ID,
        STEP_TWO_ID,
        STEP_THREE_ID,
    )


def test_workflow_specification_preserves_step_order() -> None:
    workflow = create_workflow()

    assert workflow.step_ids[0] == STEP_ONE_ID
    assert workflow.step_ids[1] == STEP_TWO_ID
    assert workflow.step_ids[2] == STEP_THREE_ID


def test_workflow_metadata_defaults_version() -> None:
    metadata = WorkflowMetadata(
        name="Simple workflow",
        description="A simple workflow used by a test.",
    )

    assert metadata.version == "1.0.0"


def test_workflow_metadata_rejects_empty_fields() -> None:
    with pytest.raises(ValidationError):
        WorkflowMetadata(
            name="",
            description="Valid description.",
        )

    with pytest.raises(ValidationError):
        WorkflowMetadata(
            name="Valid name",
            description="",
        )


def test_workflow_specification_is_immutable() -> None:
    workflow = create_workflow()

    with pytest.raises(ValidationError):
        workflow.step_ids = ()


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
        step_ids=(),
    )

    assert workflow.step_ids == ()

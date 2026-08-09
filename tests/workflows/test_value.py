"""Tests for workflow values."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import WorkflowValue, WorkflowValueBinding

STEP_ID = UUID("44df6bdb-2d5e-4564-8ab3-d5c53abfd84d")


def test_workflow_value_records_name_value_and_producer() -> None:
    workflow_value = WorkflowValue(
        name="classification",
        value="math",
        producer_step_id=STEP_ID,
    )

    assert workflow_value.name == "classification"
    assert workflow_value.value == "math"
    assert workflow_value.producer_step_id == STEP_ID


def test_workflow_value_accepts_structured_objects() -> None:
    workflow_value = WorkflowValue(
        name="result",
        value={
            "score": 0.97,
            "category": "support",
        },
        producer_step_id=STEP_ID,
    )

    assert workflow_value.value == {
        "score": 0.97,
        "category": "support",
    }


def test_workflow_value_is_immutable() -> None:
    workflow_value = WorkflowValue(
        name="classification",
        value="math",
        producer_step_id=STEP_ID,
    )

    with pytest.raises(ValidationError):
        workflow_value.name = "intent"


def test_workflow_value_round_trips_through_json() -> None:
    workflow_value = WorkflowValue(
        name="classification",
        value={
            "category": "math",
            "confidence": 0.98,
        },
        producer_step_id=STEP_ID,
    )

    restored = WorkflowValue.model_validate_json(workflow_value.model_dump_json())

    assert restored == workflow_value


def test_workflow_value_binding_records_name_and_path() -> None:
    binding = WorkflowValueBinding(
        name="classification",
        path=("category",),
    )

    assert binding.name == "classification"
    assert binding.path == ("category",)


def test_workflow_value_binding_defaults_to_entire_output() -> None:
    binding = WorkflowValueBinding(
        name="result",
    )

    assert binding.path == ()


def test_workflow_value_binding_supports_nested_paths() -> None:
    binding = WorkflowValueBinding(
        name="first_label",
        path=(
            "predictions",
            0,
            "label",
        ),
    )

    assert binding.path == (
        "predictions",
        0,
        "label",
    )


def test_workflow_value_binding_is_immutable() -> None:
    binding = WorkflowValueBinding(
        name="classification",
        path=("category",),
    )

    with pytest.raises(ValidationError):
        binding.path = ()


def test_workflow_value_binding_round_trips_through_json() -> None:
    binding = WorkflowValueBinding(
        name="classification",
        path=(
            "result",
            "category",
        ),
    )

    restored = WorkflowValueBinding.model_validate_json(binding.model_dump_json())

    assert restored == binding


def test_workflow_value_round_trips_structured_json() -> None:
    workflow_value = WorkflowValue(
        name="classification",
        value={
            "category": "math",
            "confidence": 0.98,
            "alternatives": [
                "reasoning",
                "general",
            ],
        },
        producer_step_id=STEP_ID,
    )

    restored = WorkflowValue.model_validate_json(workflow_value.model_dump_json())

    assert restored == workflow_value

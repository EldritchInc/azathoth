"""Tests for workflow values."""

from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.workflows import (
    WorkflowInputBinding,
    WorkflowValue,
    WorkflowValueBinding,
    WorkflowValueReference,
    WorkflowValueResolutionError,
)

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


def test_workflow_value_binding_resolves_entire_output() -> None:
    binding = WorkflowValueBinding(
        name="result",
    )

    output: JsonValue = {
        "category": "math",
        "confidence": 0.98,
    }

    assert binding.resolve(output) == output


def test_workflow_value_binding_resolves_object_field() -> None:
    binding = WorkflowValueBinding(
        name="classification",
        path=("category",),
    )

    assert (
        binding.resolve(
            {
                "category": "math",
                "confidence": 0.98,
            }
        )
        == "math"
    )


def test_workflow_value_binding_resolves_nested_path() -> None:
    binding = WorkflowValueBinding(
        name="label",
        path=(
            "predictions",
            0,
            "label",
        ),
    )

    output: JsonValue = {
        "predictions": [
            {
                "label": "math",
            }
        ]
    }

    assert binding.resolve(output) == "math"


def test_workflow_value_binding_rejects_missing_object_key() -> None:
    binding = WorkflowValueBinding(
        name="classification",
        path=("category",),
    )

    with pytest.raises(
        WorkflowValueResolutionError,
        match="missing object key",
    ):
        binding.resolve(
            {
                "confidence": 0.98,
            }
        )


def test_workflow_value_binding_rejects_index_on_non_list() -> None:
    binding = WorkflowValueBinding(
        name="label",
        path=(0,),
    )

    with pytest.raises(
        WorkflowValueResolutionError,
        match="expected a list",
    ):
        binding.resolve(
            {
                "label": "math",
            }
        )


def test_workflow_value_binding_rejects_out_of_range_index() -> None:
    binding = WorkflowValueBinding(
        name="label",
        path=(1,),
    )

    with pytest.raises(
        WorkflowValueResolutionError,
        match="out of range",
    ):
        binding.resolve(
            [
                "math",
            ]
        )


def test_workflow_value_reference_records_producer_and_name() -> None:
    reference = WorkflowValueReference(
        producer_step_id=STEP_ID,
        name="classification",
    )

    assert reference.producer_step_id == STEP_ID
    assert reference.name == "classification"


def test_workflow_value_reference_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="",
        )


def test_workflow_value_reference_is_immutable() -> None:
    reference = WorkflowValueReference(
        producer_step_id=STEP_ID,
        name="classification",
    )

    with pytest.raises(ValidationError):
        reference.name = "intent"


def test_workflow_value_reference_round_trips_through_json() -> None:
    reference = WorkflowValueReference(
        producer_step_id=STEP_ID,
        name="classification",
    )

    restored = WorkflowValueReference.model_validate_json(reference.model_dump_json())

    assert restored == reference


def test_workflow_value_references_distinguish_same_name_by_producer() -> None:
    other_step_id = UUID("f95a21c2-3fcb-4ca5-bbbc-7192f5c3b1be")

    first = WorkflowValueReference(
        producer_step_id=STEP_ID,
        name="classification",
    )
    second = WorkflowValueReference(
        producer_step_id=other_step_id,
        name="classification",
    )

    assert first != second


def test_workflow_input_binding_records_name_and_source() -> None:
    binding = WorkflowInputBinding(
        name="classification",
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
    )

    assert binding.name == "classification"
    assert binding.source == WorkflowValueReference(
        producer_step_id=STEP_ID,
        name="classification",
    )


def test_workflow_input_binding_can_alias_source_value() -> None:
    binding = WorkflowInputBinding(
        name="route",
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
    )

    assert binding.name == "route"
    assert binding.source.name == "classification"


def test_workflow_input_binding_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowInputBinding(
            name="",
            source=WorkflowValueReference(
                producer_step_id=STEP_ID,
                name="classification",
            ),
        )


def test_workflow_input_binding_is_immutable() -> None:
    binding = WorkflowInputBinding(
        name="classification",
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
    )

    with pytest.raises(ValidationError):
        binding.name = "route"


def test_workflow_input_binding_round_trips_through_json() -> None:
    binding = WorkflowInputBinding(
        name="route",
        source=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
    )

    restored = WorkflowInputBinding.model_validate_json(binding.model_dump_json())

    assert restored == binding

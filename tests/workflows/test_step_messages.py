"""Tests for workflow step messages and value emission declarations."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.revisions import content_digest
from azathoth.tools import ToolRequirement
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    decode_workflow_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

WORKFLOW_EXAMPLES = PROJECT_ROOT / "examples" / "workflows"

STEP_ID = UUID("b2000000-0000-4000-8000-000000000011")

COUNT_OUTPUT = (
    WorkflowValueBinding(
        name="count",
        path=("count",),
    ),
)

#
# Digests of the checked-in workflow examples computed before steps could
# declare messages. Unset presentation fields must never change them.
#
EXAMPLE_DIGESTS = {
    "classify-sentiment.json": "7798b7c4977eec125c49bac1f41a491d1e2ef6d3d40ba0d2e0047fe9c3c15f4e",
    "redundant-word-count.json": "5a7b3500ab70bb4bbcb1c10e67db329d308e840594a411bba8df803941315cb9",
    "simple-prompt.json": "7782dc067a693bd8dbf9785fef6fe48030bab9ad9a3197c5695b60d718823577",
}


def create_step(
    *,
    message: str | None = None,
    emit_values: bool = False,
    outputs: tuple[WorkflowValueBinding, ...] = COUNT_OUTPUT,
) -> WorkflowStepSpecification:
    """Create one tool step with the given presentation fields."""

    return WorkflowStepSpecification(
        id=STEP_ID,
        specification=ToolStepSpecification(
            requirement=ToolRequirement(
                name="word_count",
                version="1.0.0",
                runtime="python",
            ),
        ),
        outputs=outputs,
        message=message,
        emit_values=emit_values,
    )


def test_step_is_silent_by_default() -> None:
    step = create_step()

    assert step.message is None
    assert step.emit_values is False


def test_step_accepts_a_message() -> None:
    step = create_step(
        message="Counting words",
    )

    assert step.message == "Counting words"
    assert step.emit_values is False


def test_step_with_a_message_may_emit_its_values() -> None:
    step = create_step(
        message="Counting words",
        emit_values=True,
    )

    assert step.emit_values is True


def test_step_rejects_an_empty_message() -> None:
    with pytest.raises(ValidationError):
        create_step(
            message="",
        )


def test_step_rejects_emitting_values_without_a_message() -> None:
    with pytest.raises(
        ValidationError,
        match=f"Workflow step {STEP_ID} emits values but declares no message\\.",
    ):
        create_step(
            emit_values=True,
        )


def test_step_rejects_emitting_values_without_outputs() -> None:
    with pytest.raises(
        ValidationError,
        match=f"Workflow step {STEP_ID} emits values but declares no outputs\\.",
    ):
        create_step(
            message="Counting words",
            emit_values=True,
            outputs=(),
        )


def test_unset_presentation_fields_are_omitted_from_serialization() -> None:
    serialized = create_step().model_dump(
        mode="json",
    )

    assert "message" not in serialized
    assert "emit_values" not in serialized


def test_set_presentation_fields_are_serialized() -> None:
    serialized = create_step(
        message="Counting words",
        emit_values=True,
    ).model_dump(
        mode="json",
    )

    assert serialized["message"] == "Counting words"
    assert serialized["emit_values"] is True


def test_message_without_value_emission_omits_only_emit_values() -> None:
    serialized = create_step(
        message="Counting words",
    ).model_dump(
        mode="json",
    )

    assert serialized["message"] == "Counting words"
    assert "emit_values" not in serialized


def test_step_with_presentation_fields_round_trips_through_json() -> None:
    step = create_step(
        message="Counting words",
        emit_values=True,
    )

    assert WorkflowStepSpecification.model_validate_json(step.model_dump_json()) == step


def test_step_recorded_before_messages_existed_still_decodes() -> None:
    document = json.loads(
        create_step(
            message="Counting words",
            emit_values=True,
        ).model_dump_json()
    )

    del document["message"]
    del document["emit_values"]

    step = WorkflowStepSpecification.model_validate(document)

    assert step.message is None
    assert step.emit_values is False


def test_message_is_part_of_step_content_identity() -> None:
    assert content_digest(
        create_step(
            message="Counting words",
        )
    ) != content_digest(create_step())


def test_existing_workflow_example_digests_are_unchanged() -> None:
    for name, expected in EXAMPLE_DIGESTS.items():
        specification = decode_workflow_document(
            (WORKFLOW_EXAMPLES / name).read_text(
                encoding="utf-8",
            )
        )

        assert content_digest(specification) == expected, name

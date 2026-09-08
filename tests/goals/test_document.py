"""Tests for portable reusable goal documents."""

import json
from uuid import UUID

import pytest

from azathoth.goals import (
    Goal,
    GoalDocumentError,
    decode_goal_document,
    encode_goal_document,
)

GOAL_ID = UUID("11111111-1111-1111-1111-111111111111")


def create_goal() -> Goal:
    """Create one portable reusable goal."""

    return Goal(
        id=GOAL_ID,
        name="Answer accurately",
        description=("Produce the correct answer for the supplied request."),
        success_criteria=(
            "The answer matches the expected result.",
            "The answer remains factual.",
        ),
        constraints=(
            "Do not rely on unavailable external state.",
            "Remain provider independent.",
        ),
    )


def test_encode_goal_document_produces_readable_json() -> None:
    encoded = encode_goal_document(
        create_goal(),
    )

    payload = json.loads(encoded)

    assert payload["id"] == str(GOAL_ID)
    assert payload["name"] == "Answer accurately"

    assert payload["success_criteria"] == [
        "The answer matches the expected result.",
        "The answer remains factual.",
    ]

    assert payload["constraints"] == [
        "Do not rely on unavailable external state.",
        "Remain provider independent.",
    ]

    assert encoded.startswith("{\n")
    assert '\n  "success_criteria": [' in encoded
    assert '\n  "constraints": [' in encoded


def test_goal_document_round_trips_complete_goal() -> None:
    original = create_goal()

    restored = decode_goal_document(encode_goal_document(original))

    assert restored == original
    assert restored is not original


def test_goal_document_preserves_success_criteria_order() -> None:
    restored = decode_goal_document(
        encode_goal_document(
            create_goal(),
        )
    )

    assert restored.success_criteria == (
        "The answer matches the expected result.",
        "The answer remains factual.",
    )


def test_goal_document_preserves_constraint_order() -> None:
    restored = decode_goal_document(
        encode_goal_document(
            create_goal(),
        )
    )

    assert restored.constraints == (
        "Do not rely on unavailable external state.",
        "Remain provider independent.",
    )


def test_decode_goal_document_rejects_malformed_json() -> None:
    with pytest.raises(
        GoalDocumentError,
        match="Goal document is not a valid Goal",
    ):
        decode_goal_document("{this is definitely not json")


def test_decode_goal_document_rejects_wrong_document_shape() -> None:
    with pytest.raises(
        GoalDocumentError,
        match="Goal document is not a valid Goal",
    ):
        decode_goal_document('{"hello":"eldritch"}')


def test_decode_goal_document_rejects_empty_success_criteria() -> None:
    goal = create_goal().model_dump(
        mode="json",
    )

    goal["success_criteria"] = []

    with pytest.raises(
        GoalDocumentError,
        match="Goal document is not a valid Goal",
    ):
        decode_goal_document(json.dumps(goal))


def test_decode_goal_document_rejects_invalid_domain_data() -> None:
    goal = create_goal().model_dump(
        mode="json",
    )

    goal["name"] = ""

    with pytest.raises(
        GoalDocumentError,
        match="Goal document is not a valid Goal",
    ):
        decode_goal_document(json.dumps(goal))


def test_goal_document_error_preserves_validation_cause() -> None:
    try:
        decode_goal_document('{"invalid":true}')
    except GoalDocumentError as exc:
        assert exc.__cause__ is not None
    else:
        raise AssertionError("Expected invalid goal document to fail.")

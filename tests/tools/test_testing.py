"""Tests for durable tool verification models."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.tools import ToolTestCase

TEST_CASE_ID = UUID("11111111-1111-1111-1111-111111111111")
TOOL_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_test_case() -> ToolTestCase:
    """Create a deterministic tool test case."""

    return ToolTestCase(
        id=TEST_CASE_ID,
        tool_id=TOOL_ID,
        name="counts two words",
        description="Verify a two-word string is counted correctly.",
        inputs={
            "text": "hello world",
        },
        expected_output={
            "count": 2,
        },
    )


def test_tool_test_case_records_contract() -> None:
    test_case = create_test_case()

    assert test_case.id == TEST_CASE_ID
    assert test_case.tool_id == TOOL_ID
    assert test_case.name == "counts two words"
    assert test_case.description == "Verify a two-word string is counted correctly."
    assert test_case.inputs == {
        "text": "hello world",
    }
    assert test_case.expected_output == {
        "count": 2,
    }


def test_tool_test_case_generates_identifier() -> None:
    test_case = ToolTestCase(
        tool_id=TOOL_ID,
        name="counts two words",
        description="Verify a two-word string is counted correctly.",
        inputs={
            "text": "hello world",
        },
        expected_output={
            "count": 2,
        },
    )

    assert isinstance(test_case.id, UUID)


def test_tool_test_case_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ToolTestCase(
            tool_id=TOOL_ID,
            name="",
            description="Verify a two-word string is counted correctly.",
            inputs={},
            expected_output={},
        )


def test_tool_test_case_rejects_empty_description() -> None:
    with pytest.raises(ValidationError):
        ToolTestCase(
            tool_id=TOOL_ID,
            name="counts two words",
            description="",
            inputs={},
            expected_output={},
        )


def test_tool_test_case_is_immutable() -> None:
    test_case = create_test_case()

    with pytest.raises(ValidationError):
        test_case.name = "changed"


def test_tool_test_case_round_trips_through_json() -> None:
    test_case = create_test_case()

    restored = ToolTestCase.model_validate_json(
        test_case.model_dump_json(),
    )

    assert restored == test_case

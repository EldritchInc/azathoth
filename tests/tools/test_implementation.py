"""Tests for durable tool implementation models."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.tools import ToolImplementation

IMPLEMENTATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")
TOOL_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_implementation() -> ToolImplementation:
    """Create a deterministic tool implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        source=("def word_count(text: str) -> int:\n    return len(text.split())\n"),
    )


def test_tool_implementation_records_metadata() -> None:
    implementation = create_implementation()

    assert implementation.id == IMPLEMENTATION_ID
    assert implementation.tool_id == TOOL_ID
    assert implementation.tool_version == "1.0.0"
    assert implementation.version == "1.0.0"
    assert implementation.runtime == "python"
    assert implementation.source == (
        "def word_count(text: str) -> int:\n    return len(text.split())\n"
    )


def test_tool_implementation_generates_identifier() -> None:
    implementation = ToolImplementation(
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime="python",
        source="return 1",
    )

    assert isinstance(implementation.id, UUID)


def test_tool_implementation_defaults_version() -> None:
    implementation = ToolImplementation(
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime="python",
        source="return 1",
    )

    assert implementation.version == "1.0.0"


def test_tool_implementation_rejects_empty_tool_version() -> None:
    with pytest.raises(ValidationError):
        ToolImplementation(
            tool_id=TOOL_ID,
            tool_version="",
            runtime="python",
            source="return 1",
        )


def test_tool_implementation_rejects_empty_version() -> None:
    with pytest.raises(ValidationError):
        ToolImplementation(
            tool_id=TOOL_ID,
            tool_version="1.0.0",
            version="",
            runtime="python",
            source="return 1",
        )


def test_tool_implementation_rejects_empty_runtime() -> None:
    with pytest.raises(ValidationError):
        ToolImplementation(
            tool_id=TOOL_ID,
            tool_version="1.0.0",
            runtime="",
            source="return 1",
        )


def test_tool_implementation_rejects_empty_source() -> None:
    with pytest.raises(ValidationError):
        ToolImplementation(
            tool_id=TOOL_ID,
            tool_version="1.0.0",
            runtime="python",
            source="",
        )


def test_tool_implementation_is_immutable() -> None:
    implementation = create_implementation()

    with pytest.raises(ValidationError):
        implementation.version = "2.0.0"


def test_tool_implementation_round_trips_through_json() -> None:
    implementation = create_implementation()

    restored = ToolImplementation.model_validate_json(
        implementation.model_dump_json(),
    )

    assert restored == implementation


def test_tool_can_have_multiple_implementations() -> None:
    first = create_implementation()
    second = ToolImplementation(
        id=SECOND_IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="javascript",
        source="const wordCount = text => text.trim().split(/\\s+/).length;\n",
    )

    assert first.tool_id == second.tool_id
    assert first.tool_version == second.tool_version
    assert first.id != second.id
    assert first.runtime != second.runtime


def test_tool_implementation_can_evolve_without_changing_tool_version() -> None:
    first = create_implementation()
    second = ToolImplementation(
        id=SECOND_IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.1.0",
        runtime="python",
        source=(
            "def word_count(text: str) -> int:\n"
            "    return len(text.strip().split()) if text.strip() else 0\n"
        ),
    )

    assert first.tool_id == second.tool_id
    assert first.tool_version == second.tool_version
    assert first.version == "1.0.0"
    assert second.version == "1.1.0"

"""Tests for durable tool contract models."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.tools import (
    ToolDefinition,
    ToolInputSchema,
    ToolOutputSchema,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")


def create_input_schema() -> ToolInputSchema:
    """Create a deterministic tool input schema."""

    return ToolInputSchema(
        json_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                },
            },
            "required": ["text"],
        },
    )


def create_output_schema() -> ToolOutputSchema:
    """Create a deterministic tool output schema."""

    return ToolOutputSchema(
        json_schema={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                },
            },
            "required": ["count"],
        },
    )


def create_tool_definition() -> ToolDefinition:
    """Create a deterministic tool definition."""

    return ToolDefinition(
        id=TOOL_ID,
        name="word_count",
        description="Count the words in a text input.",
        version="1.0.0",
        input_schema=create_input_schema(),
        output_schema=create_output_schema(),
    )


def test_tool_definition_records_contract() -> None:
    tool = create_tool_definition()

    assert tool.id == TOOL_ID
    assert tool.name == "word_count"
    assert tool.description == "Count the words in a text input."
    assert tool.version == "1.0.0"
    assert tool.input_schema == create_input_schema()
    assert tool.output_schema == create_output_schema()


def test_tool_definition_generates_identifier() -> None:
    tool = ToolDefinition(
        name="word_count",
        description="Count the words in a text input.",
        input_schema=create_input_schema(),
        output_schema=create_output_schema(),
    )

    assert isinstance(tool.id, UUID)


def test_tool_definition_defaults_version() -> None:
    tool = ToolDefinition(
        name="word_count",
        description="Count the words in a text input.",
        input_schema=create_input_schema(),
        output_schema=create_output_schema(),
    )

    assert tool.version == "1.0.0"


def test_tool_definition_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ToolDefinition(
            name="",
            description="Count the words in a text input.",
            input_schema=create_input_schema(),
            output_schema=create_output_schema(),
        )


def test_tool_definition_rejects_empty_description() -> None:
    with pytest.raises(ValidationError):
        ToolDefinition(
            name="word_count",
            description="",
            input_schema=create_input_schema(),
            output_schema=create_output_schema(),
        )


def test_tool_definition_rejects_empty_version() -> None:
    with pytest.raises(ValidationError):
        ToolDefinition(
            name="word_count",
            description="Count the words in a text input.",
            version="",
            input_schema=create_input_schema(),
            output_schema=create_output_schema(),
        )


def test_tool_definition_is_immutable() -> None:
    tool = create_tool_definition()

    with pytest.raises(ValidationError):
        tool.version = "2.0.0"


def test_tool_input_schema_is_immutable() -> None:
    schema = create_input_schema()

    with pytest.raises(ValidationError):
        schema.json_schema = {}


def test_tool_output_schema_is_immutable() -> None:
    schema = create_output_schema()

    with pytest.raises(ValidationError):
        schema.json_schema = {}


def test_tool_definition_round_trips_through_json() -> None:
    tool = create_tool_definition()

    restored = ToolDefinition.model_validate_json(tool.model_dump_json())

    assert restored == tool


def test_tool_input_schema_preserves_json_schema() -> None:
    schema = create_input_schema()

    assert schema.json_schema == {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
            },
        },
        "required": ["text"],
    }


def test_tool_output_schema_preserves_json_schema() -> None:
    schema = create_output_schema()

    assert schema.json_schema == {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
            },
        },
        "required": ["count"],
    }

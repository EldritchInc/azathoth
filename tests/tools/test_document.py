"""Tests for portable durable tool documents."""

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.tools import (
    ToolDefinition,
    ToolDocument,
    ToolDocumentError,
    ToolImplementation,
    ToolInputSchema,
    ToolOutputSchema,
    ToolTestCase,
    decode_tool_document,
    encode_tool_document,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

OTHER_TOOL_ID = UUID("22222222-2222-2222-2222-222222222222")

IMPLEMENTATION_ID = UUID("33333333-3333-3333-3333-333333333333")

TEST_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_definition() -> ToolDefinition:
    """Create one portable durable tool definition."""

    return ToolDefinition(
        id=TOOL_ID,
        name="word_count",
        description="Count whitespace-delimited words.",
        version="1.0.0",
        input_schema=ToolInputSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                    },
                },
                "required": [
                    "text",
                ],
            }
        ),
        output_schema=ToolOutputSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                    },
                },
                "required": [
                    "count",
                ],
            }
        ),
    )


def create_implementation(
    *,
    tool_id: UUID = TOOL_ID,
    tool_version: str = "1.0.0",
) -> ToolImplementation:
    """Create one portable durable tool implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=tool_id,
        tool_version=tool_version,
        version="1.0.0",
        runtime="python",
        entrypoint="run",
        source=("def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"),
    )


def create_test_case(
    *,
    tool_id: UUID = TOOL_ID,
) -> ToolTestCase:
    """Create one portable durable tool test case."""

    return ToolTestCase(
        id=TEST_CASE_ID,
        tool_id=tool_id,
        name="counts two words",
        description="Verify a two-word input.",
        inputs={
            "text": "hello world",
        },
        expected_output={
            "count": 2,
        },
    )


def create_document() -> ToolDocument:
    """Create one complete portable durable tool document."""

    return ToolDocument(
        definition=create_definition(),
        implementations=(create_implementation(),),
        test_cases=(create_test_case(),),
    )


def test_tool_document_records_complete_durable_tool_package() -> None:
    document = create_document()

    assert document.definition == create_definition()

    assert document.implementations == (create_implementation(),)

    assert document.test_cases == (create_test_case(),)


def test_tool_document_allows_definition_without_implementations() -> None:
    document = ToolDocument(
        definition=create_definition(),
        test_cases=(create_test_case(),),
    )

    assert document.implementations == ()


def test_tool_document_allows_definition_without_test_cases() -> None:
    document = ToolDocument(
        definition=create_definition(),
        implementations=(create_implementation(),),
    )

    assert document.test_cases == ()


def test_tool_document_rejects_implementation_for_other_tool() -> None:
    with pytest.raises(
        ValidationError,
        match="implementation",
    ):
        ToolDocument(
            definition=create_definition(),
            implementations=(
                create_implementation(
                    tool_id=OTHER_TOOL_ID,
                ),
            ),
        )


def test_tool_document_rejects_implementation_for_other_tool_version() -> None:
    with pytest.raises(
        ValidationError,
        match="implementation",
    ):
        ToolDocument(
            definition=create_definition(),
            implementations=(
                create_implementation(
                    tool_version="2.0.0",
                ),
            ),
        )


def test_tool_document_rejects_test_case_for_other_tool() -> None:
    with pytest.raises(
        ValidationError,
        match="test case",
    ):
        ToolDocument(
            definition=create_definition(),
            test_cases=(
                create_test_case(
                    tool_id=OTHER_TOOL_ID,
                ),
            ),
        )


def test_tool_document_is_immutable() -> None:
    document = create_document()

    with pytest.raises(ValidationError):
        document.implementations = ()


def test_tool_document_round_trips_through_json() -> None:
    original = create_document()

    restored = ToolDocument.model_validate_json(
        original.model_dump_json(),
    )

    assert restored == original


def test_encode_tool_document_produces_readable_json() -> None:
    encoded = encode_tool_document(
        create_document(),
    )

    payload = json.loads(encoded)

    assert payload["definition"]["id"] == str(TOOL_ID)
    assert payload["definition"]["version"] == "1.0.0"

    assert payload["implementations"][0]["id"] == (str(IMPLEMENTATION_ID))

    assert payload["test_cases"][0]["id"] == (str(TEST_CASE_ID))

    assert encoded.startswith("{\n")
    assert '\n  "definition": {' in encoded
    assert '\n  "implementations": [' in encoded
    assert '\n  "test_cases": [' in encoded


def test_decode_tool_document_round_trips_complete_document() -> None:
    original = create_document()

    restored = decode_tool_document(encode_tool_document(original))

    assert restored == original
    assert restored is not original


def test_decode_tool_document_rejects_malformed_json() -> None:
    with pytest.raises(
        ToolDocumentError,
        match="Tool document is not valid",
    ):
        decode_tool_document("{this is definitely not json")


def test_decode_tool_document_rejects_wrong_document_shape() -> None:
    with pytest.raises(
        ToolDocumentError,
        match="Tool document is not valid",
    ):
        decode_tool_document('{"hello":"eldritch"}')


def test_decode_tool_document_rejects_invalid_domain_relationships() -> None:
    document = create_document().model_dump(
        mode="json",
    )

    document["implementations"][0]["tool_version"] = "9.0.0"

    with pytest.raises(
        ToolDocumentError,
        match="Tool document is not valid",
    ):
        decode_tool_document(json.dumps(document))


def test_tool_document_error_preserves_validation_cause() -> None:
    try:
        decode_tool_document('{"invalid":true}')
    except ToolDocumentError as exc:
        assert exc.__cause__ is not None
    else:
        raise AssertionError("Expected invalid tool document to fail.")

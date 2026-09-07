"""Tests for the checked-in portable tool document example."""

from pathlib import Path
from uuid import UUID

from azathoth.tools import (
    ToolDefinition,
    ToolDocument,
    ToolImplementation,
    ToolInputSchema,
    ToolOutputSchema,
    ToolTestCase,
    decode_tool_document,
    encode_tool_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

WORD_COUNT_DOCUMENT = PROJECT_ROOT / "examples" / "tools" / "word-count.json"

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_TEST_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_TEST_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_expected_document() -> ToolDocument:
    """Create the domain model represented by the checked-in example."""

    return ToolDocument(
        definition=ToolDefinition(
            id=TOOL_ID,
            name="word_count",
            description=("Count whitespace-delimited words in supplied text."),
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
        ),
        implementations=(
            ToolImplementation(
                id=IMPLEMENTATION_ID,
                tool_id=TOOL_ID,
                tool_version="1.0.0",
                version="1.0.0",
                runtime="python",
                entrypoint="run",
                source=(
                    "def run(text: str) -> dict[str, int]:\n"
                    "    return {'count': len(text.split())}\n"
                ),
            ),
        ),
        test_cases=(
            ToolTestCase(
                id=FIRST_TEST_CASE_ID,
                tool_id=TOOL_ID,
                name="counts two words",
                description="Verify a two-word input.",
                inputs={
                    "text": "hello world",
                },
                expected_output={
                    "count": 2,
                },
            ),
            ToolTestCase(
                id=SECOND_TEST_CASE_ID,
                tool_id=TOOL_ID,
                name="counts empty input",
                description="Verify an empty input.",
                inputs={
                    "text": "",
                },
                expected_output={
                    "count": 0,
                },
            ),
        ),
    )


def test_checked_in_tool_example_decodes_to_expected_document() -> None:
    encoded = WORD_COUNT_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert (
        decode_tool_document(
            encoded,
        )
        == create_expected_document()
    )


def test_checked_in_tool_example_matches_canonical_encoding() -> None:
    encoded = WORD_COUNT_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert encoded.rstrip("\n") == encode_tool_document(
        create_expected_document(),
    )

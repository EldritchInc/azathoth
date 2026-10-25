"""Tests for process tool implementation models and their digests."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.revisions import content_digest
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    ToolImplementation,
    decode_tool_document,
    encode_tool_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

WORD_COUNT_DOCUMENT = PROJECT_ROOT / "examples" / "tools" / "word-count.json"

#
# Digests of the word-count example computed before process implementations
# existed. Unset process fields must never change them.
#
WORD_COUNT_DOCUMENT_DIGEST = "522fc826932dc62413505b41610d02417246743f39430e98fbf3efad19ddaf76"

WORD_COUNT_IMPLEMENTATION_DIGEST = (
    "3a19c822621dd53c24df91fdd44c50479e6ebde95bb80a1cb057b011fb16a5f8"
)

TOOL_ID = UUID("2c3d4e5f-6a7b-4c8d-8e9f-1a2b3c4d5e01")

IMPLEMENTATION_ID = UUID("2c3d4e5f-6a7b-4c8d-8e9f-1a2b3c4d5e11")

SCRIPT = "import json, sys\nprint(json.dumps(json.load(sys.stdin)))\n"

PYTHON_COMMAND = ("python3",)


def create_process_implementation(
    *,
    command: tuple[str, ...] | None = PYTHON_COMMAND,
    timeout_seconds: float | None = None,
) -> ToolImplementation:
    """Create one process implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=PROCESS_TOOL_RUNTIME,
        source=SCRIPT,
        command=command,
        timeout_seconds=timeout_seconds,
    )


def test_process_implementation_records_command_and_timeout() -> None:
    implementation = create_process_implementation(
        timeout_seconds=30.0,
    )

    assert implementation.command == ("python3",)
    assert implementation.timeout_seconds == 30.0


def test_process_implementation_requires_a_command() -> None:
    with pytest.raises(
        ValidationError,
        match="Process tool implementations must declare a command.",
    ):
        create_process_implementation(
            command=None,
        )


def test_process_implementation_rejects_an_empty_command() -> None:
    with pytest.raises(ValidationError):
        create_process_implementation(
            command=(),
        )


def test_process_implementation_rejects_empty_command_arguments() -> None:
    with pytest.raises(
        ValidationError,
        match="Process tool implementation command arguments cannot be empty.",
    ):
        create_process_implementation(
            command=(
                "python3",
                "",
            ),
        )


def test_process_implementation_rejects_a_non_positive_timeout() -> None:
    with pytest.raises(ValidationError):
        create_process_implementation(
            timeout_seconds=0.0,
        )


def test_python_implementation_rejects_a_command() -> None:
    with pytest.raises(
        ValidationError,
        match="Only process tool implementations may declare a command or timeout.",
    ):
        ToolImplementation(
            tool_id=TOOL_ID,
            tool_version="1.0.0",
            runtime="python",
            source="def run():\n    return {}\n",
            command=PYTHON_COMMAND,
        )


def test_python_implementation_rejects_a_timeout() -> None:
    with pytest.raises(
        ValidationError,
        match="Only process tool implementations may declare a command or timeout.",
    ):
        ToolImplementation(
            tool_id=TOOL_ID,
            tool_version="1.0.0",
            runtime="python",
            source="def run():\n    return {}\n",
            timeout_seconds=5.0,
        )


def test_python_implementation_serializes_without_process_fields() -> None:
    dumped = ToolImplementation(
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime="python",
        source="def run():\n    return {}\n",
    ).model_dump(
        mode="json",
    )

    assert "command" not in dumped
    assert "timeout_seconds" not in dumped


def test_process_implementation_serializes_its_process_fields() -> None:
    dumped = json.loads(
        create_process_implementation(
            timeout_seconds=2.5,
        ).model_dump_json(),
    )

    assert dumped["command"] == ["python3"]
    assert dumped["timeout_seconds"] == 2.5


def test_process_implementation_without_timeout_omits_it() -> None:
    dumped = create_process_implementation().model_dump(
        mode="json",
    )

    assert dumped["command"] == ["python3"]
    assert "timeout_seconds" not in dumped


def test_process_implementation_round_trips_through_json() -> None:
    implementation = create_process_implementation(
        timeout_seconds=2.5,
    )

    assert ToolImplementation.model_validate_json(implementation.model_dump_json()) == (
        implementation
    )


def test_implementation_json_without_process_fields_still_decodes() -> None:
    implementation = ToolImplementation.model_validate_json(
        json.dumps(
            {
                "id": str(IMPLEMENTATION_ID),
                "tool_id": str(TOOL_ID),
                "tool_version": "1.0.0",
                "version": "1.0.0",
                "runtime": "python",
                "entrypoint": "run",
                "source": "def run():\n    return {}\n",
            }
        )
    )

    assert implementation.command is None
    assert implementation.timeout_seconds is None


def test_existing_tool_document_digest_is_unchanged() -> None:
    document = decode_tool_document(
        WORD_COUNT_DOCUMENT.read_text(
            encoding="utf-8",
        )
    )

    assert content_digest(document) == WORD_COUNT_DOCUMENT_DIGEST


def test_existing_tool_implementation_digest_is_unchanged() -> None:
    document = decode_tool_document(
        WORD_COUNT_DOCUMENT.read_text(
            encoding="utf-8",
        )
    )

    assert content_digest(document.implementations[0]) == WORD_COUNT_IMPLEMENTATION_DIGEST


def test_existing_tool_document_encodes_unchanged() -> None:
    encoded = WORD_COUNT_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert encode_tool_document(decode_tool_document(encoded)).rstrip("\n") == (
        encoded.rstrip("\n")
    )

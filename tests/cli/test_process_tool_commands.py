"""Tests for importing, showing and verifying process tools through the CLI."""

import shlex
import sys
from pathlib import Path

import pytest

from azathoth.cli import (
    import_tool,
    show_tool_implementation,
    verify_tool,
)
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    SQLiteToolRepository,
    ToolDocument,
    ToolImplementation,
)
from tests.cli.test_tool_import import (
    IMPLEMENTATION_ID,
    TOOL_ID,
    configure_database,
    create_definition,
    create_test_case,
    write_document,
)

PROCESS_COMMAND = (
    sys.executable,
    "-u",
)

WORD_COUNT_SCRIPT = (
    "import json, sys\n"
    "inputs = json.load(sys.stdin)\n"
    "print(json.dumps({'count': len(inputs['text'].split())}))\n"
)


def create_process_implementation() -> ToolImplementation:
    """Create one process implementation of the word-count tool."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime=PROCESS_TOOL_RUNTIME,
        source=WORD_COUNT_SCRIPT,
        command=PROCESS_COMMAND,
        timeout_seconds=30.0,
    )


def import_process_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Import the process word-count tool and return its database."""

    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "tool.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    write_document(
        document_path,
        ToolDocument(
            definition=create_definition(),
            implementations=(create_process_implementation(),),
            test_cases=(create_test_case(),),
        ),
    )

    assert import_tool(document_path) == 0

    return database


def test_tool_import_accepts_and_persists_a_process_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = import_process_tool(
        tmp_path,
        monkeypatch,
    )

    assert capsys.readouterr().err == ""

    assert (
        SQLiteToolRepository(
            database,
        ).get_implementation(
            IMPLEMENTATION_ID,
        )
        == create_process_implementation()
    )


def test_tool_implementation_show_renders_command_and_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import_process_tool(
        tmp_path,
        monkeypatch,
    )

    capsys.readouterr()

    assert show_tool_implementation(IMPLEMENTATION_ID) == 0

    captured = capsys.readouterr()

    assert "Runtime: process\n" in captured.out
    assert f"Command: {shlex.join(PROCESS_COMMAND)}\n" in captured.out
    assert "Timeout: 30 seconds\n" in captured.out
    assert "inputs = json.load(sys.stdin)" in captured.out


def test_tool_verify_passes_a_process_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import_process_tool(
        tmp_path,
        monkeypatch,
    )

    capsys.readouterr()

    result = verify_tool(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert "Runtime: process" in captured.out
    assert "Status: passed" in captured.out

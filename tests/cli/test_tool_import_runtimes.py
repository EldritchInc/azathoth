"""Tests for rejecting unexecutable tool runtimes at import."""

from pathlib import Path

import pytest

from azathoth.cli import import_tool
from azathoth.tools import (
    ToolDocument,
    unsupported_runtime_message,
)
from tests.cli.test_tool_import import (
    configure_database,
    create_definition,
    create_implementation,
    create_test_case,
    write_document,
)


def test_tool_import_rejects_an_unsupported_runtime_before_creating_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "tool.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    implementation = create_implementation().model_copy(
        update={
            "runtime": "javascript",
        }
    )

    write_document(
        document_path,
        ToolDocument(
            definition=create_definition(),
            implementations=(implementation,),
            test_cases=(create_test_case(),),
        ),
    )

    result = import_tool(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"{unsupported_runtime_message(implementation)}\n"

    assert not database.exists()


def test_tool_import_accepts_a_supported_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(
        database=tmp_path / "azathoth.db",
        monkeypatch=monkeypatch,
    )

    document_path = tmp_path / "tool.json"

    write_document(
        document_path,
    )

    assert import_tool(document_path) == 0

    assert capsys.readouterr().err == ""

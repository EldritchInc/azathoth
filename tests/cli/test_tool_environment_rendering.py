"""Tests for showing a process implementation's environment grants (ADR 0099)."""

from pathlib import Path

import pytest

from azathoth.cli import import_tool, show_tool_implementation
from azathoth.tools import ToolDocument
from tests.cli.test_process_tool_commands import create_process_implementation
from tests.cli.test_tool_import import (
    IMPLEMENTATION_ID,
    configure_database,
    create_definition,
    create_test_case,
    write_document,
)


def show_imported_implementation(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    environment: tuple[str, ...],
) -> str:
    """Import the process word-count tool with the given grants, then show it."""

    document_path = tmp_path / "tool.json"

    configure_database(database=tmp_path / "azathoth.db", monkeypatch=monkeypatch)

    write_document(
        document_path,
        ToolDocument(
            definition=create_definition(),
            implementations=(
                create_process_implementation().model_copy(
                    update={"environment": environment},
                ),
            ),
            test_cases=(create_test_case(),),
        ),
    )

    assert import_tool(document_path) == 0

    capsys.readouterr()

    assert show_tool_implementation(IMPLEMENTATION_ID) == 0

    captured = capsys.readouterr()

    assert captured.err == ""

    return captured.out


def test_implementation_show_names_the_grants_in_order_after_the_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = show_imported_implementation(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        environment=("OPENROUTER_API_KEY", "AWS_*"),
    )

    assert "Timeout: 30 seconds\nEnvironment: OPENROUTER_API_KEY, AWS_*\nSource:\n" in output


def test_implementation_show_omits_the_environment_without_grants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = show_imported_implementation(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        environment=(),
    )

    assert "Environment" not in output

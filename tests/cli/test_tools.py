"""Tests for durable tool inspection commands."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    list_tool_versions,
    list_tools,
    show_tool,
)
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDefinition,
    ToolInputSchema,
    ToolOutputSchema,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_TOOL_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_definition(
    *,
    tool_id: UUID = TOOL_ID,
    name: str = "word_count",
    version: str = "1.0.0",
) -> ToolDefinition:
    """Create one durable tool definition."""

    return ToolDefinition(
        id=tool_id,
        name=name,
        description=f"{name} capability.",
        version=version,
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


def configure_repository(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    definitions: tuple[ToolDefinition, ...],
) -> None:
    """Persist definitions and configure the CLI database."""

    repository = SQLiteToolRepository(database)

    for definition in definitions:
        repository.save_definition(definition)

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def test_tool_list_prints_all_definition_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(
            create_definition(
                version="1.0.0",
            ),
            create_definition(
                version="2.0.0",
            ),
            create_definition(
                tool_id=SECOND_TOOL_ID,
                name="sentence_count",
            ),
        ),
    )

    result = list_tools()

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (
        f"{TOOL_ID}  1.0.0  word_count\n"
        f"{TOOL_ID}  2.0.0  word_count\n"
        f"{SECOND_TOOL_ID}  1.0.0  sentence_count\n"
    )

    assert captured.err == ""


def test_tool_list_prints_nothing_when_repository_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(),
    )

    assert list_tools() == 0

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""


def test_tool_show_prints_exact_definition_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    first = create_definition(
        version="1.0.0",
    )

    second = create_definition(
        version="2.0.0",
    )

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(
            first,
            second,
        ),
    )

    result = show_tool(
        TOOL_ID,
        version="2.0.0",
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert f"ID: {TOOL_ID}\n" in captured.out
    assert "Name: word_count\n" in captured.out
    assert "Version: 2.0.0\n" in captured.out
    assert "Description: word_count capability.\n" in captured.out

    assert "Input Schema:\n" in captured.out
    assert '"text": {' in captured.out

    assert "Output Schema:\n" in captured.out
    assert '"count": {' in captured.out


def test_tool_show_rejects_unknown_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(create_definition(),),
    )

    result = show_tool(
        TOOL_ID,
        version="9.0.0",
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Tool {TOOL_ID}@9.0.0 is not configured.\n")


def test_tool_versions_lists_versions_in_durable_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(
            create_definition(
                version="2.0.0",
            ),
            create_definition(
                version="1.0.0",
            ),
            create_definition(
                version="3.0.0",
            ),
            create_definition(
                tool_id=SECOND_TOOL_ID,
                name="sentence_count",
            ),
        ),
    )

    result = list_tool_versions(
        TOOL_ID,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ("2.0.0\n1.0.0\n3.0.0\n")
    assert captured.err == ""


def test_tool_versions_rejects_unknown_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        definitions=(),
    )

    result = list_tool_versions(
        TOOL_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Tool {TOOL_ID} is not configured.\n")

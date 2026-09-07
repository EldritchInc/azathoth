"""Tests for portable tool import through the CLI."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    import_tool,
)
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDefinition,
    ToolDocument,
    ToolImplementation,
    ToolInputSchema,
    ToolOutputSchema,
    ToolTestCase,
    encode_tool_document,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")

TEST_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_definition() -> ToolDefinition:
    """Create one durable imported tool definition."""

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


def create_implementation() -> ToolImplementation:
    """Create one durable imported implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        entrypoint="run",
        source=("def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"),
    )


def create_test_case() -> ToolTestCase:
    """Create one durable imported test case."""

    return ToolTestCase(
        id=TEST_CASE_ID,
        tool_id=TOOL_ID,
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
    """Create one complete imported tool document."""

    return ToolDocument(
        definition=create_definition(),
        implementations=(create_implementation(),),
        test_cases=(create_test_case(),),
    )


def configure_database(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure one CLI database."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def write_document(
    path: Path,
    document: ToolDocument | None = None,
) -> None:
    """Write one portable tool document."""

    path.write_text(
        encode_tool_document(
            document or create_document(),
        ),
        encoding="utf-8",
    )


def test_tool_import_persists_complete_document(
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

    write_document(
        document_path,
    )

    result = import_tool(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert captured.out == (f"Imported tool {TOOL_ID}@1.0.0.\n")

    repository = SQLiteToolRepository(
        database,
    )

    assert (
        repository.get_definition(
            TOOL_ID,
            "1.0.0",
        )
        == create_definition()
    )

    assert (
        repository.get_implementation(
            IMPLEMENTATION_ID,
        )
        == create_implementation()
    )

    assert (
        repository.get_test_case(
            TEST_CASE_ID,
        )
        == create_test_case()
    )


def test_tool_import_rejects_missing_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "missing.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = import_tool(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "Unable to read tool document" in captured.err

    assert not database.exists()


def test_tool_import_rejects_invalid_document_before_creating_database(
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

    document_path.write_text(
        '{"hello":"eldritch"}',
        encoding="utf-8",
    )

    result = import_tool(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == ("Tool document is not valid.\n")

    assert not database.exists()


def test_tool_import_rejects_duplicate_definition_without_partial_import(
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

    repository = SQLiteToolRepository(
        database,
    )

    repository.save_definition(
        create_definition(),
    )

    write_document(
        document_path,
    )

    result = import_tool(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Tool definition {TOOL_ID}@1.0.0 already exists.\n")

    assert repository.implementations() == ()
    assert repository.test_cases() == ()


def test_tool_import_rejects_duplicate_implementation_without_partial_import(
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

    repository = SQLiteToolRepository(
        database,
    )

    repository.save_implementation(
        create_implementation(),
    )

    write_document(
        document_path,
    )

    result = import_tool(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Tool implementation {IMPLEMENTATION_ID} already exists.\n")

    assert repository.definitions() == ()
    assert repository.test_cases() == ()


def test_tool_import_rejects_duplicate_test_case_without_partial_import(
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

    repository = SQLiteToolRepository(
        database,
    )

    repository.save_test_case(
        create_test_case(),
    )

    write_document(
        document_path,
    )

    result = import_tool(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Tool test case {TEST_CASE_ID} already exists.\n")

    assert repository.definitions() == ()
    assert repository.implementations() == ()

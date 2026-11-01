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

    assert captured.out == (f"Imported tool {TOOL_ID}@1.0.0 revision 1.\n")

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


OTHER_TOOL_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_changed_document() -> ToolDocument:
    """Create the document with changed implementation source and no test case."""

    return ToolDocument(
        definition=create_definition(),
        implementations=(
            create_implementation().model_copy(
                update={
                    "source": (
                        "def run(text: str) -> dict[str, int]:\n"
                        "    return {'count': len(text.strip().split())}\n"
                    ),
                },
            ),
        ),
    )


RENAMED_IMPLEMENTATION_ID = UUID("55555555-5555-5555-5555-555555555555")


def create_renamed_document(
    version: str,
) -> ToolDocument:
    """Create a different tool, `line_count`, that reuses this tool's ID at one version."""

    return ToolDocument(
        definition=create_definition().model_copy(
            update={
                "name": "line_count",
                "description": "Count lines.",
                "version": version,
            },
        ),
        implementations=(
            create_implementation().model_copy(
                update={
                    "id": RENAMED_IMPLEMENTATION_ID,
                    "tool_version": version,
                },
            ),
        ),
    )


def import_document(
    tmp_path: Path,
    document: ToolDocument,
    *,
    name: str = "tool.json",
) -> int:
    """Write one document and import it."""

    path = tmp_path / name

    write_document(
        path,
        document,
    )

    return import_tool(path)


def test_tool_reimport_appends_an_identical_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    assert import_document(tmp_path, create_document()) == 0
    assert import_document(tmp_path, create_document()) == 0

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out.splitlines() == [
        f"Imported tool {TOOL_ID}@1.0.0 revision 1.",
        f"Imported tool {TOOL_ID}@1.0.0 revision 2 (identical to revision 1).",
    ]

    repository = SQLiteToolRepository(database)

    assert repository.implementations() == (create_implementation(),)
    assert repository.test_cases() == (create_test_case(),)


def test_tool_import_of_a_changed_document_makes_its_artifacts_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    import_document(tmp_path, create_document())
    import_document(tmp_path, create_changed_document(), name="changed.json")

    lines = capsys.readouterr().out.splitlines()

    assert lines[-1] == f"Imported tool {TOOL_ID}@1.0.0 revision 2."

    repository = SQLiteToolRepository(database)

    assert repository.implementations() == create_changed_document().implementations
    assert repository.test_cases() == ()


def test_tool_reimport_of_earlier_content_restores_its_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    import_document(tmp_path, create_document())
    import_document(tmp_path, create_changed_document(), name="changed.json")
    import_document(tmp_path, create_document())

    lines = capsys.readouterr().out.splitlines()

    assert lines[-1] == f"Imported tool {TOOL_ID}@1.0.0 revision 3 (identical to revision 1)."

    repository = SQLiteToolRepository(database)

    assert repository.implementations() == (create_implementation(),)
    assert repository.test_cases() == (create_test_case(),)


def test_tool_import_records_artifacts_saved_before_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    repository = SQLiteToolRepository(database)

    repository.save_definition(create_definition())
    repository.save_implementation(create_implementation())

    assert import_document(tmp_path, create_document()) == 0

    assert capsys.readouterr().out == f"Imported tool {TOOL_ID}@1.0.0 revision 2.\n"

    first, second = repository.document_revisions(TOOL_ID)

    assert first.imported_at is None
    assert first.document == ToolDocument(
        definition=create_definition(),
        implementations=(create_implementation(),),
    )
    assert second.document == create_document()


def test_tool_import_rejects_an_implementation_of_another_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    repository = SQLiteToolRepository(database)

    repository.save_implementation(
        create_implementation().model_copy(
            update={
                "tool_id": OTHER_TOOL_ID,
            },
        )
    )

    result = import_document(tmp_path, create_document())

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (
        f"Tool implementation {IMPLEMENTATION_ID} belongs to tool {OTHER_TOOL_ID}@1.0.0.\n"
    )

    assert repository.definitions() == ()
    assert repository.test_cases() == ()
    assert repository.document_revisions(TOOL_ID) == ()


def test_tool_import_rejects_an_implementation_of_another_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    import_document(tmp_path, create_document())

    capsys.readouterr()

    second_version = ToolDocument(
        definition=create_definition().model_copy(
            update={
                "version": "2.0.0",
            },
        ),
        implementations=(
            create_implementation().model_copy(
                update={
                    "tool_version": "2.0.0",
                },
            ),
        ),
    )

    result = import_document(tmp_path, second_version, name="second.json")

    captured = capsys.readouterr()

    assert result == 1
    assert captured.err == (
        f"Tool implementation {IMPLEMENTATION_ID} belongs to tool {TOOL_ID}@1.0.0.\n"
    )

    assert SQLiteToolRepository(database).get_definition(TOOL_ID, "2.0.0") is None


def test_tool_import_rejects_a_test_case_of_another_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    repository = SQLiteToolRepository(database)

    repository.save_test_case(
        create_test_case().model_copy(
            update={
                "tool_id": OTHER_TOOL_ID,
            },
        )
    )

    result = import_document(tmp_path, create_document())

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Tool test case {TEST_CASE_ID} belongs to tool {OTHER_TOOL_ID}.\n"

    assert repository.definitions() == ()
    assert repository.implementations() == ()


def test_tool_import_rejects_a_different_tool_that_reuses_a_tool_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    import_document(tmp_path, create_document())

    capsys.readouterr()

    result = import_document(tmp_path, create_renamed_document("1.0.0"), name="renamed.json")

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (
        f"Tool {TOOL_ID} is named 'word_count'; a document cannot rename it to 'line_count'.\n"
    )

    repository = SQLiteToolRepository(database)

    assert repository.get_implementation(RENAMED_IMPLEMENTATION_ID) is None
    assert len(repository.document_revisions(TOOL_ID)) == 1


def test_the_cli_readme_documents_the_real_rename_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(database=tmp_path / "azathoth.db", monkeypatch=monkeypatch)

    import_document(tmp_path, create_document())
    import_document(tmp_path, create_renamed_document("1.0.0"), name="renamed.json")

    message = capsys.readouterr().err.splitlines()[-1]

    documented = (
        message.replace(str(TOOL_ID), "<TOOL_ID>")
        .replace("'word_count'", "'<NAME>'")
        .replace("'line_count'", "'<NEW_NAME>'")
    )

    readme = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"

    assert f"\n{documented}\n" in readme.read_text(encoding="utf-8")

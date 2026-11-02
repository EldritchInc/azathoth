"""Tests for installing the standard tool library through the CLI (ADR 0095)."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    build_parser,
    import_tool,
    install_standard_tools,
    main,
)
from azathoth.standard import standard_tool_documents
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDocument,
    encode_tool_document,
)
from tests.cli.test_tool_import import configure_database

OTHER_TOOL_ID = UUID("c9000000-0000-4000-8000-000000000001")

INSTALLED = (
    "Installed tool run_workflow@1.0.0 revision 1.\n"
    "Installed tool loop_workflow@1.1.0 revision 1.\n"
    "Installed tool json_select@1.0.0 revision 1.\n"
    "Installed tool json_object@1.0.0 revision 1.\n"
    "Installed tool json_merge@1.0.0 revision 1.\n"
    "Installed tool validate_json@1.0.0 revision 1.\n"
    "Installed tool chunk_text@1.0.0 revision 1.\n"
    "Installed tool join_text@1.0.0 revision 1.\n"
    "Installed tool render_template@1.0.0 revision 1.\n"
)

ALREADY_INSTALLED = (
    "Tool run_workflow@1.0.0 is already installed (revision 1).\n"
    "Tool loop_workflow@1.1.0 is already installed (revision 1).\n"
    "Tool json_select@1.0.0 is already installed (revision 1).\n"
    "Tool json_object@1.0.0 is already installed (revision 1).\n"
    "Tool json_merge@1.0.0 is already installed (revision 1).\n"
    "Tool validate_json@1.0.0 is already installed (revision 1).\n"
    "Tool chunk_text@1.0.0 is already installed (revision 1).\n"
    "Tool join_text@1.0.0 is already installed (revision 1).\n"
    "Tool render_template@1.0.0 is already installed (revision 1).\n"
)


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Configure an empty CLI database and return its path."""

    path = tmp_path / "azathoth.db"

    configure_database(
        database=path,
        monkeypatch=monkeypatch,
    )

    return path


def standard_document(
    name: str,
) -> ToolDocument:
    """Return the standard document of one tool by name."""

    (document,) = (
        document for document in standard_tool_documents() if document.definition.name == name
    )

    return document


def revision_numbers(
    database: Path,
) -> list[tuple[str, int]]:
    """Return `(name, revision)` for every recorded revision of the standard tools."""

    repository = SQLiteToolRepository(database)

    return [
        (revision.document.definition.name, revision.number)
        for document in standard_tool_documents()
        for revision in repository.document_revisions(document.definition.id)
    ]


def modified_loop_document() -> ToolDocument:
    """Return the standard loop tool with an operator's edited description."""

    document = standard_document("loop_workflow")

    return document.model_copy(
        update={
            "definition": document.definition.model_copy(
                update={"description": "An operator's local copy."},
            ),
        },
    )


def write_document(
    path: Path,
    document: ToolDocument,
) -> Path:
    """Write one tool document and return its path."""

    path.write_text(encode_tool_document(document), encoding="utf-8")

    return path


def test_install_standard_parser_records_the_action() -> None:
    arguments = build_parser().parse_args(("tool", "install-standard"))

    assert arguments.tool_action == "install-standard"


def test_tool_help_lists_install_standard(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(("tool", "--help"))

    assert exit_info.value.code == 0
    assert "install-standard" in capsys.readouterr().out


def test_install_imports_every_standard_tool_as_its_first_revision(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert install_standard_tools() == 0

    captured = capsys.readouterr()

    assert captured.out == INSTALLED
    assert captured.err == ""

    repository = SQLiteToolRepository(database)

    for document in standard_tool_documents():
        latest = repository.latest_document_revision(
            document.definition.id,
            document.definition.version,
        )

        assert latest is not None
        assert latest.number == 1
        assert latest.document == document


def test_install_makes_the_standard_implementations_current(
    database: Path,
) -> None:
    assert install_standard_tools() == 0

    repository = SQLiteToolRepository(database)

    for document in standard_tool_documents():
        for implementation in document.implementations:
            assert repository.get_implementation(implementation.id) == implementation


def test_installing_again_writes_nothing(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert install_standard_tools() == 0

    capsys.readouterr()

    assert install_standard_tools() == 0

    captured = capsys.readouterr()

    assert captured.out == ALREADY_INSTALLED
    assert captured.err == ""
    assert revision_numbers(database) == [
        ("run_workflow", 1),
        ("loop_workflow", 1),
        ("json_select", 1),
        ("json_object", 1),
        ("json_merge", 1),
        ("validate_json", 1),
        ("chunk_text", 1),
        ("join_text", 1),
        ("render_template", 1),
    ]


def test_install_skips_a_tool_already_imported_from_the_same_document(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_tool = write_document(tmp_path / "run-workflow.json", standard_document("run_workflow"))

    assert import_tool(run_tool) == 0

    capsys.readouterr()

    assert install_standard_tools() == 0

    assert capsys.readouterr().out == (
        "Tool run_workflow@1.0.0 is already installed (revision 1).\n"
        "Installed tool loop_workflow@1.1.0 revision 1.\n"
        "Installed tool json_select@1.0.0 revision 1.\n"
        "Installed tool json_object@1.0.0 revision 1.\n"
        "Installed tool json_merge@1.0.0 revision 1.\n"
        "Installed tool validate_json@1.0.0 revision 1.\n"
        "Installed tool chunk_text@1.0.0 revision 1.\n"
        "Installed tool join_text@1.0.0 revision 1.\n"
        "Installed tool render_template@1.0.0 revision 1.\n"
    )


def test_install_appends_a_revision_over_a_modified_copy(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    modified = write_document(tmp_path / "loop-workflow.json", modified_loop_document())

    assert import_tool(modified) == 0

    capsys.readouterr()

    assert install_standard_tools() == 0

    assert capsys.readouterr().out == (
        "Installed tool run_workflow@1.0.0 revision 1.\n"
        "Installed tool loop_workflow@1.1.0 revision 2.\n"
        "Installed tool json_select@1.0.0 revision 1.\n"
        "Installed tool json_object@1.0.0 revision 1.\n"
        "Installed tool json_merge@1.0.0 revision 1.\n"
        "Installed tool validate_json@1.0.0 revision 1.\n"
        "Installed tool chunk_text@1.0.0 revision 1.\n"
        "Installed tool join_text@1.0.0 revision 1.\n"
        "Installed tool render_template@1.0.0 revision 1.\n"
    )

    loop = standard_document("loop_workflow")

    latest = SQLiteToolRepository(database).latest_document_revision(
        loop.definition.id,
        loop.definition.version,
    )

    assert latest is not None
    assert latest.number == 2
    assert latest.document == loop


def test_install_notes_a_revision_identical_to_an_earlier_one(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert install_standard_tools() == 0

    modified = write_document(tmp_path / "loop-workflow.json", modified_loop_document())

    assert import_tool(modified) == 0

    capsys.readouterr()

    assert install_standard_tools() == 0

    assert capsys.readouterr().out == (
        "Tool run_workflow@1.0.0 is already installed (revision 1).\n"
        "Installed tool loop_workflow@1.1.0 revision 3 (identical to revision 1).\n"
        "Tool json_select@1.0.0 is already installed (revision 1).\n"
        "Tool json_object@1.0.0 is already installed (revision 1).\n"
        "Tool json_merge@1.0.0 is already installed (revision 1).\n"
        "Tool validate_json@1.0.0 is already installed (revision 1).\n"
        "Tool chunk_text@1.0.0 is already installed (revision 1).\n"
        "Tool join_text@1.0.0 is already installed (revision 1).\n"
        "Tool render_template@1.0.0 is already installed (revision 1).\n"
    )
    assert revision_numbers(database) == [
        ("run_workflow", 1),
        ("loop_workflow", 1),
        ("loop_workflow", 2),
        ("loop_workflow", 3),
        ("json_select", 1),
        ("json_object", 1),
        ("json_merge", 1),
        ("validate_json", 1),
        ("chunk_text", 1),
        ("join_text", 1),
        ("render_template", 1),
    ]


def test_install_fails_when_another_tool_holds_a_standard_implementation_id(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = standard_document("run_workflow")
    (implementation,) = run.implementations

    SQLiteToolRepository(database).save_document(
        ToolDocument(
            definition=run.definition.model_copy(update={"id": OTHER_TOOL_ID}),
            implementations=(implementation.model_copy(update={"tool_id": OTHER_TOOL_ID}),),
        )
    )

    assert install_standard_tools() == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        f"Tool implementation {implementation.id} belongs to tool {OTHER_TOOL_ID}@1.0.0.\n"
    )
    assert revision_numbers(database) == []


def test_install_stops_at_a_different_tool_that_holds_a_standard_tool_id(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    select = standard_document("json_select")
    (implementation,) = select.implementations

    SQLiteToolRepository(database).save_document(
        ToolDocument(
            definition=select.definition.model_copy(update={"name": "countdown_step"}),
            implementations=(implementation.model_copy(update={"id": OTHER_TOOL_ID}),),
        )
    )

    assert install_standard_tools() == 1

    captured = capsys.readouterr()

    assert captured.out == (
        "Installed tool run_workflow@1.0.0 revision 1.\n"
        "Installed tool loop_workflow@1.1.0 revision 1.\n"
    )
    assert captured.err == (
        f"Tool {select.definition.id} is named 'countdown_step'; "
        "a document cannot rename it to 'json_select'.\n"
    )
    assert revision_numbers(database) == [
        ("run_workflow", 1),
        ("loop_workflow", 1),
        ("countdown_step", 1),
    ]


def test_main_dispatches_install_standard(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(("tool", "install-standard")) == 0

    assert capsys.readouterr().out == INSTALLED

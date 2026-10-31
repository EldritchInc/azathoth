"""Tests for `azathoth init` (ADR 0095)."""

import re
from pathlib import Path

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    build_parser,
    import_tool,
    initialize_database,
    main,
)
from azathoth.standard import standard_tool_documents
from azathoth.tools import SQLiteToolRepository
from tests.cli.test_tool_import import (
    TOOL_ID,
    configure_database,
    write_document,
)
from tests.cli.test_tool_install_standard import (
    ALREADY_INSTALLED,
    INSTALLED,
)


def configure(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Point the CLI at one database path and return it."""

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    return database


def test_init_parser_records_the_command() -> None:
    arguments = build_parser().parse_args(("init",))

    assert arguments.command == "init"


def test_help_lists_init(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(("--help",))

    assert exit_info.value.code == 0
    output = capsys.readouterr().out

    assert re.search(r"^\s+init\s+Create the database", output, re.MULTILINE) is not None


def test_init_creates_the_database_and_installs_the_standard_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(tmp_path / "azathoth.db", monkeypatch)

    assert initialize_database() == 0

    captured = capsys.readouterr()

    assert captured.out == f"Database: {database} (created)\n{INSTALLED}"
    assert captured.err == ""
    assert database.is_file()

    repository = SQLiteToolRepository(database)

    for document in standard_tool_documents():
        latest = repository.latest_document_revision(
            document.definition.id,
            document.definition.version,
        )

        assert latest is not None
        assert latest.document == document


def test_init_creates_missing_parent_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(tmp_path / "data" / "nested" / "azathoth.db", monkeypatch)

    assert initialize_database() == 0

    assert capsys.readouterr().out.startswith(f"Database: {database} (created)\n")
    assert database.is_file()


def test_init_again_changes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(tmp_path / "azathoth.db", monkeypatch)

    assert initialize_database() == 0

    capsys.readouterr()

    assert initialize_database() == 0

    captured = capsys.readouterr()

    assert captured.out == f"Database: {database} (existing)\n{ALREADY_INSTALLED}"
    assert captured.err == ""

    repository = SQLiteToolRepository(database)

    for document in standard_tool_documents():
        assert len(repository.document_revisions(document.definition.id)) == 1


def test_init_keeps_an_existing_databases_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(tmp_path / "azathoth.db", monkeypatch)

    word_count = tmp_path / "word-count.json"
    write_document(word_count)

    assert import_tool(word_count) == 0

    capsys.readouterr()

    assert initialize_database() == 0

    assert capsys.readouterr().out == f"Database: {database} (existing)\n{INSTALLED}"
    assert len(SQLiteToolRepository(database).document_revisions(TOOL_ID)) == 1


def test_init_uses_the_default_database_in_the_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(DATABASE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)

    assert initialize_database() == 0

    database = Path.cwd() / "azathoth.db"

    assert capsys.readouterr().out == f"Database: {database} (created)\n{INSTALLED}"
    assert database.is_file()


def test_init_shows_a_relative_database_as_an_absolute_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    configure(Path("state") / "azathoth.db", monkeypatch)

    assert initialize_database() == 0

    database = Path.cwd() / "state" / "azathoth.db"

    assert capsys.readouterr().out.startswith(f"Database: {database} (created)\n")
    assert database.is_file()


def test_init_fails_when_the_database_cannot_be_opened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(tmp_path / "azathoth.db", monkeypatch)
    database.mkdir()

    assert initialize_database() == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err.startswith(f"Unable to open database {database}: ")


def test_main_dispatches_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(tmp_path / "azathoth.db", monkeypatch)

    assert main(("init",)) == 0

    assert capsys.readouterr().out == f"Database: {database} (created)\n{INSTALLED}"

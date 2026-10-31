"""Tests for inspecting and exporting imported tool revisions."""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    build_parser,
    export_tool,
    import_tool,
    list_tool_history,
)
from azathoth.cli.dispatching import dispatch_tool_command
from azathoth.revisions import content_digest
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDocumentRevision,
    encode_tool_document,
)
from tests.cli.test_tool_import import (
    TOOL_ID,
    configure_database,
    create_changed_document,
    create_document,
)
from tests.tools.test_tool_revision_repository import create_second_version_document
from tests.workflows.test_workflow_revision_lineage import (
    create_catalog,
    create_runtime,
    run_candidate,
)

UNKNOWN_TOOL_ID = UUID("99999999-9999-4999-8999-999999999999")


def save_history(
    database: Path,
) -> tuple[ToolDocumentRevision, ...]:
    """Import version 1.0.0 three times, reverting the change, then version 2.0.0."""

    repository = SQLiteToolRepository(database)

    return (
        repository.save_document(create_document()),
        repository.save_document(create_changed_document()),
        repository.save_document(create_document()),
        repository.save_document(create_second_version_document()),
    )


def history_line(
    revision: ToolDocumentRevision,
    *,
    note: str = "",
) -> str:
    """Return the expected history line of one revision."""

    imported = revision.imported_at.isoformat() if revision.imported_at else "unknown"

    return (
        f"{revision.tool_version}  {revision.number}  {imported}  "
        f"{revision.content_digest[:12]}  "
        f"{len(revision.document.implementations)} implementations  "
        f"{len(revision.document.test_cases)} test cases{note}"
    )


def unused(
    *_arguments: object,
    **_keywords: object,
) -> int:
    """Fail when an unrelated tool handler is dispatched."""

    raise AssertionError("unrelated tool handler should not be dispatched")


def dispatch(
    arguments: Namespace,
    *,
    export_tool: Callable[..., int] = unused,
    list_tool_history: Callable[..., int] = unused,
) -> int | None:
    """Dispatch one tool command with only the revision handlers live."""

    return dispatch_tool_command(
        arguments,
        export_tool=export_tool,
        import_tool=unused,
        install_standard_tools=unused,
        list_tool_history=list_tool_history,
        list_tool_implementations=unused,
        list_tool_test_cases=unused,
        list_tool_versions=unused,
        list_tools=unused,
        show_tool=unused,
        show_tool_implementation=unused,
        show_tool_test_case=unused,
        tool_usage=unused,
        verify_tool=unused,
    )


def test_history_parser_records_tool_without_filters() -> None:
    arguments = build_parser().parse_args(
        (
            "tool",
            "history",
            str(TOOL_ID),
        )
    )

    assert arguments.tool_action == "history"
    assert arguments.tool_id == TOOL_ID
    assert arguments.tool_history_version is None
    assert arguments.tool_history_limit is None


def test_history_parser_records_version_and_limit() -> None:
    arguments = build_parser().parse_args(
        (
            "tool",
            "history",
            str(TOOL_ID),
            "--version",
            "1.0.0",
            "--limit",
            "2",
        )
    )

    assert arguments.tool_history_version == "1.0.0"
    assert arguments.tool_history_limit == 2


def test_export_parser_requires_a_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(
            (
                "tool",
                "export",
                str(TOOL_ID),
            )
        )

    assert raised.value.code == 2
    assert "--version" in capsys.readouterr().err


def test_export_parser_records_version_and_revision() -> None:
    arguments = build_parser().parse_args(
        (
            "tool",
            "export",
            str(TOOL_ID),
            "--version",
            "1.0.0",
            "--revision",
            "2",
        )
    )

    assert arguments.tool_action == "export"
    assert arguments.tool_version == "1.0.0"
    assert arguments.tool_revision == 2


def test_history_dispatch_passes_version_and_limit() -> None:
    calls: list[tuple[UUID, str | None, int | None]] = []

    def history(
        tool_id: UUID,
        *,
        version: str | None,
        limit: int | None,
    ) -> int:
        calls.append((tool_id, version, limit))

        return 5

    result = dispatch(
        Namespace(
            tool_action="history",
            tool_id=TOOL_ID,
            tool_history_version="1.0.0",
            tool_history_limit=3,
        ),
        list_tool_history=history,
    )

    assert result == 5
    assert calls == [(TOOL_ID, "1.0.0", 3)]


def test_export_dispatch_passes_version_and_revision() -> None:
    calls: list[tuple[UUID, str, int | None]] = []

    def export(
        tool_id: UUID,
        *,
        version: str,
        revision: int | None,
    ) -> int:
        calls.append((tool_id, version, revision))

        return 6

    result = dispatch(
        Namespace(
            tool_action="export",
            tool_id=TOOL_ID,
            tool_version="2.0.0",
            tool_revision=None,
        ),
        export_tool=export,
    )

    assert result == 6
    assert calls == [(TOOL_ID, "2.0.0", None)]


def test_history_lists_every_version_newest_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    first, changed, reverted, second_version = save_history(database)

    status = list_tool_history(TOOL_ID)

    captured = capsys.readouterr()

    assert status == 0
    assert captured.err == ""
    assert captured.out.splitlines() == [
        history_line(second_version),
        history_line(reverted, note="  identical to revision 1"),
        history_line(changed),
        history_line(first),
    ]


def test_history_filters_by_version_and_applies_the_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    _first, changed, reverted, _second_version = save_history(database)

    status = list_tool_history(
        TOOL_ID,
        version="1.0.0",
        limit=2,
    )

    assert status == 0
    assert capsys.readouterr().out.splitlines() == [
        history_line(reverted, note="  identical to revision 1"),
        history_line(changed),
    ]


def test_history_rejects_unknown_tools_and_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    assert list_tool_history(UNKNOWN_TOOL_ID) == 1
    assert capsys.readouterr().err == f"Tool {UNKNOWN_TOOL_ID} is not configured.\n"

    assert (
        list_tool_history(
            TOOL_ID,
            version="9.9.9",
        )
        == 1
    )

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Tool {TOOL_ID}@9.9.9 is not configured.\n"


def test_export_prints_the_latest_revision_of_a_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    status = export_tool(
        TOOL_ID,
        version="1.0.0",
    )

    captured = capsys.readouterr()

    assert status == 0
    assert captured.err == ""
    assert captured.out == encode_tool_document(create_document()) + "\n"


def test_export_selects_an_earlier_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    status = export_tool(
        TOOL_ID,
        version="1.0.0",
        revision=2,
    )

    assert status == 0
    assert capsys.readouterr().out == encode_tool_document(create_changed_document()) + "\n"


def test_exported_revisions_reimport_as_identical_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    export_tool(
        TOOL_ID,
        version="1.0.0",
        revision=2,
    )

    document = tmp_path / "revision-2.json"

    document.write_text(
        capsys.readouterr().out,
        encoding="utf-8",
    )

    status = import_tool(document)

    assert status == 0
    assert capsys.readouterr().out == (
        f"Imported tool {TOOL_ID}@1.0.0 revision 4 (identical to revision 2).\n"
    )
    assert (
        SQLiteToolRepository(database).implementations()[0]
        == (create_changed_document().implementations[0])
    )


def test_export_rejects_unknown_versions_and_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    save_history(database)

    assert export_tool(TOOL_ID, version="9.9.9") == 1
    assert capsys.readouterr().err == f"Tool {TOOL_ID}@9.9.9 is not configured.\n"

    assert export_tool(TOOL_ID, version="2.0.0", revision=2) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Tool {TOOL_ID}@2.0.0 has no revision 2.\n"


def test_tool_runs_record_the_digest_of_the_code_that_ran() -> None:
    runtime = create_runtime(create_catalog())

    run = run_candidate(
        runtime.generate_workflow_candidate(create_catalog().identifiers[0]),
    )

    (step,) = run.steps

    assert step.execution is not None

    (binding,) = step.execution.resources

    (implementation,) = runtime.tool_implementations.implementations

    assert binding.attributes["implementation_digest"] == content_digest(implementation)

"""Tests for inspecting and exporting imported workflow revisions."""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.workflow_configuration as workflow_configuration
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    build_parser,
    export_workflow,
    import_workflow,
    list_workflow_history,
    render_workflow_benchmark_execution,
    render_workflow_run,
    show_workflow,
)
from azathoth.cli.dispatching import dispatch_workflow_command
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowSpecification,
    encode_workflow_document,
)
from tests.cli.test_benchmark_execution_rendering import create_run
from tests.cli.test_workflow_import import (
    WORKFLOW_ID,
    create_workflow,
)
from tests.workflows.test_workflow_revision_lineage import (
    create_catalog,
    create_runtime,
    run_candidate,
)
from tests.workflows.test_workflow_revision_repository import create_legacy_database

UNKNOWN_WORKFLOW_ID = UUID("99999999-9999-4999-8999-999999999999")


def create_renamed_workflow() -> WorkflowSpecification:
    """Create the importable workflow under a new name."""

    workflow = create_workflow()

    return workflow.model_copy(
        update={
            "metadata": workflow.metadata.model_copy(
                update={
                    "name": "Renamed workflow",
                },
            ),
        },
    )


def configure_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at one isolated database and forbid runtime bootstrap."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    def fail_load_runtime(
        _configuration: object,
    ) -> object:
        raise AssertionError("workflow revision commands must not bootstrap the runtime")

    monkeypatch.setattr(
        workflow_configuration,
        "load_runtime",
        fail_load_runtime,
    )

    return database


def save_three_revisions(
    database: Path,
) -> None:
    """Import the workflow, rename it, then revert the rename."""

    repository = SQLiteWorkflowRepository(database)

    repository.save(create_workflow())
    repository.save(create_renamed_workflow())
    repository.save(create_workflow())


def unused(
    *_arguments: object,
    **_keywords: object,
) -> int:
    """Fail when an unrelated workflow handler is dispatched."""

    raise AssertionError("unrelated workflow handler should not be dispatched")


def dispatch(
    arguments: Namespace,
    *,
    export_workflow: Callable[..., int] = unused,
    list_workflow_history: Callable[..., int] = unused,
    show_workflow: Callable[..., int] = unused,
) -> int | None:
    """Dispatch one workflow command with only the revision handlers live."""

    return dispatch_workflow_command(
        arguments,
        export_workflow=export_workflow,
        import_workflow=unused,
        invoke_workflow=unused,
        list_workflow_experiments=unused,
        list_workflow_history=list_workflow_history,
        list_workflow_invocations=unused,
        list_workflow_revisions=unused,
        list_workflow_runs=unused,
        list_workflows=unused,
        optimize_workflow=unused,
        promote_workflow=unused,
        run_workflow=unused,
        show_workflow=show_workflow,
        show_workflow_production=unused,
    )


def test_history_parser_records_workflow_without_limit() -> None:
    arguments = build_parser().parse_args(
        (
            "workflow",
            "history",
            str(WORKFLOW_ID),
        )
    )

    assert arguments.workflow_action == "history"
    assert arguments.workflow_id == WORKFLOW_ID
    assert arguments.workflow_history_limit is None


def test_history_parser_records_limit() -> None:
    arguments = build_parser().parse_args(
        (
            "workflow",
            "history",
            str(WORKFLOW_ID),
            "--limit",
            "2",
        )
    )

    assert arguments.workflow_history_limit == 2


def test_show_parser_defaults_to_the_latest_revision() -> None:
    arguments = build_parser().parse_args(
        (
            "workflow",
            "show",
            str(WORKFLOW_ID),
        )
    )

    assert arguments.workflow_specification_revision is None


def test_show_and_export_parsers_record_a_revision() -> None:
    for action in ("show", "export"):
        arguments = build_parser().parse_args(
            (
                "workflow",
                action,
                str(WORKFLOW_ID),
                "--revision",
                "3",
            )
        )

        assert arguments.workflow_action == action
        assert arguments.workflow_specification_revision == 3


def test_revision_parsers_reject_non_positive_revisions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(
            (
                "workflow",
                "export",
                str(WORKFLOW_ID),
                "--revision",
                "0",
            )
        )

    assert raised.value.code == 2
    assert "Expected a positive integer, got '0'." in capsys.readouterr().err


def test_show_dispatch_passes_the_revision() -> None:
    calls: list[tuple[UUID, int | None]] = []

    def show(
        workflow_id: UUID,
        *,
        revision: int | None,
    ) -> int:
        calls.append((workflow_id, revision))

        return 7

    result = dispatch(
        Namespace(
            workflow_action="show",
            workflow_id=WORKFLOW_ID,
            workflow_specification_revision=2,
        ),
        show_workflow=show,
    )

    assert result == 7
    assert calls == [(WORKFLOW_ID, 2)]


def test_export_dispatch_passes_the_revision() -> None:
    calls: list[tuple[UUID, int | None]] = []

    def export(
        workflow_id: UUID,
        *,
        revision: int | None,
    ) -> int:
        calls.append((workflow_id, revision))

        return 8

    result = dispatch(
        Namespace(
            workflow_action="export",
            workflow_id=WORKFLOW_ID,
            workflow_specification_revision=None,
        ),
        export_workflow=export,
    )

    assert result == 8
    assert calls == [(WORKFLOW_ID, None)]


def test_history_dispatch_passes_the_limit() -> None:
    calls: list[tuple[UUID, int | None]] = []

    def history(
        workflow_id: UUID,
        *,
        limit: int | None,
    ) -> int:
        calls.append((workflow_id, limit))

        return 9

    result = dispatch(
        Namespace(
            workflow_action="history",
            workflow_id=WORKFLOW_ID,
            workflow_history_limit=4,
        ),
        list_workflow_history=history,
    )

    assert result == 9
    assert calls == [(WORKFLOW_ID, 4)]


def test_history_lists_revisions_newest_first_and_names_reverts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_three_revisions(database)

    revisions = SQLiteWorkflowRepository(database).revisions(WORKFLOW_ID)

    status = list_workflow_history(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert status == 0
    assert captured.err == ""
    assert captured.out.splitlines() == [
        (
            f"3  {revisions[2].imported_at.isoformat() if revisions[2].imported_at else ''}  "
            f"{revisions[2].content_digest[:12]}  1.0.0  imported workflow  "
            "identical to revision 1"
        ),
        (
            f"2  {revisions[1].imported_at.isoformat() if revisions[1].imported_at else ''}  "
            f"{revisions[1].content_digest[:12]}  1.0.0  Renamed workflow"
        ),
        (
            f"1  {revisions[0].imported_at.isoformat() if revisions[0].imported_at else ''}  "
            f"{revisions[0].content_digest[:12]}  1.0.0  imported workflow"
        ),
    ]


def test_history_applies_the_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_three_revisions(database)

    status = list_workflow_history(
        WORKFLOW_ID,
        limit=1,
    )

    lines = capsys.readouterr().out.splitlines()

    assert status == 0
    assert len(lines) == 1
    assert lines[0].startswith("3  ")


def test_history_shows_unknown_import_time_for_migrated_revisions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    create_legacy_database(
        database,
        (create_workflow(),),
    )

    status = list_workflow_history(WORKFLOW_ID)

    assert status == 0
    assert capsys.readouterr().out.startswith("1  unknown  ")


def test_history_rejects_an_unknown_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(
        monkeypatch,
        tmp_path,
    )

    status = list_workflow_history(UNKNOWN_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n"


def test_show_defaults_to_the_latest_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    repository = SQLiteWorkflowRepository(database)

    repository.save(create_workflow())
    latest = repository.save(create_renamed_workflow())

    status = show_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.startswith(
        f"ID: {WORKFLOW_ID}\n"
        "Revision: 2 of 2\n"
        f"Imported: {latest.imported_at.isoformat() if latest.imported_at else ''}\n"
        f"Content Digest: {latest.content_digest}\n"
        "Name: Renamed workflow\n"
    )


def test_show_selects_an_earlier_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_three_revisions(database)

    status = show_workflow(
        WORKFLOW_ID,
        revision=2,
    )

    output = capsys.readouterr().out

    assert status == 0
    assert "Revision: 2 of 3\n" in output
    assert "Name: Renamed workflow\n" in output


def test_show_rejects_an_unknown_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_three_revisions(database)

    status = show_workflow(
        WORKFLOW_ID,
        revision=4,
    )

    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {WORKFLOW_ID} has no revision 4.\n"


def test_show_marks_migrated_revisions_as_imported_at_an_unknown_time(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    create_legacy_database(
        database,
        (create_workflow(),),
    )

    status = show_workflow(WORKFLOW_ID)

    output = capsys.readouterr().out

    assert status == 0
    assert "Revision: 1 of 1\nImported: unknown\n" in output


def test_export_prints_the_latest_revision_as_an_importable_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_three_revisions(database)

    status = export_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert status == 0
    assert captured.err == ""
    assert captured.out == encode_workflow_document(create_workflow()) + "\n"


def test_export_selects_an_earlier_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_three_revisions(database)

    status = export_workflow(
        WORKFLOW_ID,
        revision=2,
    )

    assert status == 0
    assert capsys.readouterr().out == encode_workflow_document(create_renamed_workflow()) + "\n"


def test_exported_revisions_reimport_as_identical_revisions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_three_revisions(database)

    export_workflow(
        WORKFLOW_ID,
        revision=2,
    )

    document = tmp_path / "revision-2.json"

    document.write_text(
        capsys.readouterr().out,
        encoding="utf-8",
    )

    status = import_workflow(document)

    assert status == 0
    assert capsys.readouterr().out == (
        f"Imported workflow {WORKFLOW_ID} revision 4 (identical to revision 2).\n"
    )
    assert SQLiteWorkflowRepository(database).get(WORKFLOW_ID) == create_renamed_workflow()


def test_export_rejects_unknown_workflows_and_revisions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    save_three_revisions(database)

    assert export_workflow(UNKNOWN_WORKFLOW_ID) == 1
    assert capsys.readouterr().err == f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n"

    assert (
        export_workflow(
            WORKFLOW_ID,
            revision=9,
        )
        == 1
    )
    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Workflow {WORKFLOW_ID} has no revision 9.\n"


def test_run_rendering_names_the_executed_revision() -> None:
    candidate = create_runtime(create_catalog()).generate_workflow_candidate(
        create_catalog().identifiers[0],
    )

    rendered = render_workflow_run(run_candidate(candidate))

    assert "\nWorkflow Revision: 2\nRun ID: " in rendered


def test_run_rendering_marks_unrevisioned_runs() -> None:
    candidate = create_runtime(create_catalog()).generate_workflow_candidate(
        create_catalog().identifiers[0],
    )

    run = run_candidate(candidate).model_copy(
        update={
            "workflow_revision": None,
        },
    )

    assert "\nWorkflow Revision: unknown\n" in render_workflow_run(run)


def test_execution_rendering_names_the_judged_revision() -> None:
    execution = create_run()

    (candidate,) = execution.candidates

    revised = execution.model_copy(
        update={
            "candidates": (
                candidate.model_copy(
                    update={
                        "candidate_signature": candidate.candidate_signature.model_copy(
                            update={
                                "workflow_revision": 3,
                            },
                        ),
                    },
                ),
            ),
        },
    )

    assert "\nWorkflow Revision: 3\n" in render_workflow_benchmark_execution(revised)

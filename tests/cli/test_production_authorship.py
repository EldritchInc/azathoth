"""Tests that the command line records and shows who made each production revision (ADR 0128)."""

from datetime import timedelta
from pathlib import Path

import pytest

from azathoth.cli import (
    list_workflow_revisions,
    main,
    render_workflow_production,
    render_workflow_promotion,
    show_workflow_production,
)
from azathoth.revisions import Author
from azathoth.workflows import (
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    WorkflowProductionRevision,
)
from tests.cli import test_production_inspection_commands as inspection
from tests.cli import test_workflow_promotion_lifecycle as lifecycle

AUTHOR = Author(name="Eris Discordia", email="eris@example.com")


def authored_revision(
    *,
    restores: bool = False,
) -> WorkflowProductionRevision:
    """Return the second test revision, made by the test author, restoring the first if asked."""

    return WorkflowProductionRevision(
        id=inspection.SECOND_REVISION_ID,
        state=inspection.create_state("second-model"),
        created_at=inspection.CREATED_AT + timedelta(minutes=5),
        author=AUTHOR,
        restores=inspection.FIRST_REVISION_ID if restores else None,
    )


def save_authored_history(
    database: Path,
    *,
    restores: bool = False,
) -> None:
    """Save an unauthored first revision and an authored, active second one."""

    revisions = SQLiteWorkflowProductionRevisionRepository(database)

    revisions.save(
        WorkflowProductionRevision(
            id=inspection.FIRST_REVISION_ID,
            state=inspection.create_state("first-model"),
            created_at=inspection.CREATED_AT,
        )
    )
    revisions.save(authored_revision(restores=restores))

    SQLiteWorkflowProductionStateRepository(database).set(inspection.create_state("second-model"))


def test_promote_records_the_author_it_is_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteWorkflowRepository(database).save(lifecycle.create_workflow())
    lifecycle.configure_cli_runtime(database=database, monkeypatch=monkeypatch)
    monkeypatch.setenv("AZATHOTH_AUTHOR", str(AUTHOR))

    result = main(("workflow", "promote", str(lifecycle.WORKFLOW_ID)))

    captured = capsys.readouterr()

    (revision,) = SQLiteWorkflowProductionRevisionRepository(database).revisions_for_workflow(
        lifecycle.WORKFLOW_ID
    )

    assert result == 0
    assert revision.author == AUTHOR
    assert f"Author: {AUTHOR}\n" in captured.out


def test_promote_refuses_an_author_it_cannot_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteWorkflowRepository(database).save(lifecycle.create_workflow())
    lifecycle.configure_cli_runtime(database=database, monkeypatch=monkeypatch)
    monkeypatch.setenv("AZATHOTH_AUTHOR", "Eris <not an address>")

    result = main(("workflow", "promote", str(lifecycle.WORKFLOW_ID)))

    captured = capsys.readouterr()

    assert result == 1
    assert "AZATHOTH_AUTHOR" in captured.err
    assert SQLiteWorkflowProductionStateRepository(database).get(lifecycle.WORKFLOW_ID) is None
    assert (
        SQLiteWorkflowProductionRevisionRepository(database).revisions_for_workflow(
            lifecycle.WORKFLOW_ID
        )
        == ()
    )


def test_a_promotion_shows_its_author_before_when_it_was_made() -> None:
    rendered = render_workflow_promotion(authored_revision())

    assert f"Status: promoted\nAuthor: {AUTHOR}\nCreated At: " in rendered


def test_production_shows_the_active_revisions_author() -> None:
    rendered = render_workflow_production(
        inspection.create_state("second-model"),
        active_revision=authored_revision(),
    )

    assert f"Revision ID: {inspection.SECOND_REVISION_ID}\nAuthor: {AUTHOR}\nDeployed At: " in (
        rendered
    )
    assert "Restores:" not in rendered


def test_production_says_when_its_author_is_unknown() -> None:
    rendered = render_workflow_production(inspection.create_state(), active_revision=None)

    assert "Revision ID: unrecorded\nAuthor: unknown\nDeployed At: unknown" in rendered


def test_production_shows_what_a_rollback_restored() -> None:
    rendered = render_workflow_production(
        inspection.create_state("second-model"),
        active_revision=authored_revision(restores=True),
    )

    assert f"Author: {AUTHOR}\nRestores: {inspection.FIRST_REVISION_ID}\nDeployed At: " in rendered


def test_show_production_names_its_author(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = inspection.configure_database(monkeypatch, tmp_path)

    save_authored_history(database)

    result = show_workflow_production(inspection.WORKFLOW_ID)

    assert result == 0
    assert f"Author: {AUTHOR}\n" in capsys.readouterr().out


def test_revisions_name_each_author_and_what_each_restores(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = inspection.configure_database(monkeypatch, tmp_path)

    save_authored_history(database, restores=True)

    result = list_workflow_revisions(inspection.WORKFLOW_ID)

    second, first = capsys.readouterr().out.splitlines()

    assert result == 0
    assert second.startswith(f"{inspection.SECOND_REVISION_ID}  ")
    assert second.endswith(
        f"openrouter/second-model  by {AUTHOR}  restores {inspection.FIRST_REVISION_ID}"
    )
    assert first.endswith("openrouter/first-model")

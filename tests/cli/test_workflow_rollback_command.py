"""Tests for `azathoth workflow rollback` (ADR 0128)."""

from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.application as application
from azathoth.cli import build_parser, main, rollback_workflow
from azathoth.providers import ModelPortfolioEntry, SQLiteModelPortfolioRepository
from azathoth.revisions import Author
from azathoth.workflows import (
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
)
from tests.cli.test_production_inspection_commands import (
    FIRST_REVISION_ID,
    THIRD_REVISION_ID,
    WORKFLOW_ID,
    configure_database,
    create_state,
    save_deployment_history,
)

AUTHOR = Author(name="Eris Discordia", email="eris@example.com")


def authorize(
    database: Path,
    *models: str,
) -> None:
    """Authorize each OpenRouter model named in the database's portfolio."""

    portfolio = SQLiteModelPortfolioRepository(database)

    for model in models:
        portfolio.save(ModelPortfolioEntry(provider="openrouter", model=model))


def test_the_parser_records_the_workflow_and_no_target() -> None:
    arguments = build_parser().parse_args(("workflow", "rollback", str(WORKFLOW_ID)))

    assert arguments.workflow_action == "rollback"
    assert arguments.workflow_id == WORKFLOW_ID
    assert arguments.workflow_rollback_to is None


def test_the_parser_records_the_revision_to_restore() -> None:
    arguments = build_parser().parse_args(
        ("workflow", "rollback", str(WORKFLOW_ID), "--to", str(THIRD_REVISION_ID))
    )

    assert arguments.workflow_rollback_to == THIRD_REVISION_ID


def test_the_command_is_dispatched_with_its_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[UUID, UUID | None]] = []

    def fake_rollback_workflow(
        workflow_id: UUID,
        *,
        to: UUID | None,
    ) -> int:
        calls.append((workflow_id, to))

        return 73

    monkeypatch.setattr(application, "rollback_workflow", fake_rollback_workflow)

    result = main(("workflow", "rollback", str(WORKFLOW_ID), "--to", str(FIRST_REVISION_ID)))

    assert result == 73
    assert calls == [(WORKFLOW_ID, FIRST_REVISION_ID)]


def test_rollback_restores_the_revision_before_the_active_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(monkeypatch, tmp_path)
    monkeypatch.setenv("AZATHOTH_AUTHOR", str(AUTHOR))

    save_deployment_history(database)
    authorize(database, "first-model", "second-model", "third-model")

    result = rollback_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    restored = max(
        SQLiteWorkflowProductionRevisionRepository(database).revisions_for_workflow(WORKFLOW_ID),
        key=lambda revision: revision.created_at,
    )

    assert result == 0
    assert captured.err == ""
    assert restored.restores == FIRST_REVISION_ID
    assert restored.author == AUTHOR
    assert SQLiteWorkflowProductionStateRepository(database).get(WORKFLOW_ID) == create_state(
        "first-model"
    )
    assert (
        f"Revision ID: {restored.id}\n"
        "Status: rolled back\n"
        f"Restores: {FIRST_REVISION_ID}\n"
        f"Author: {AUTHOR}\n"
        "Created At: "
    ) in captured.out
    assert "Primary Model: openrouter/first-model" in captured.out


def test_rollback_refuses_a_model_no_longer_authorized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(monkeypatch, tmp_path)

    save_deployment_history(database)
    authorize(database, "second-model")

    result = rollback_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "openrouter/first-model, which the portfolio no longer authorizes" in captured.err
    assert SQLiteWorkflowProductionStateRepository(database).get(WORKFLOW_ID) == create_state(
        "second-model"
    )


def test_rollback_of_a_workflow_not_in_production_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(monkeypatch, tmp_path)

    result = rollback_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.err == f"Workflow {WORKFLOW_ID} is not in production.\n"


def test_rollback_refuses_an_author_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(monkeypatch, tmp_path)
    monkeypatch.setenv("AZATHOTH_AUTHOR", "Eris <not an address>")

    save_deployment_history(database)
    authorize(database, "first-model")

    result = rollback_workflow(WORKFLOW_ID)

    assert result == 1
    assert "AZATHOTH_AUTHOR" in capsys.readouterr().err
    assert SQLiteWorkflowProductionStateRepository(database).get(WORKFLOW_ID) == create_state(
        "second-model"
    )

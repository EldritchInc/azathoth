"""Tests for declared workflow results in workflow import and show commands."""

from pathlib import Path

import pytest

from azathoth.cli import (
    import_workflow,
    show_workflow,
)
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    encode_workflow_document,
)
from tests.cli.test_workflow_import import (
    STEP_ID,
    WORKFLOW_ID,
    configure_database,
    create_workflow,
)


def test_workflow_import_rejects_document_without_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document = tmp_path / "workflow.json"

    document.write_text(
        encode_workflow_document(
            create_workflow().model_copy(
                update={
                    "result": None,
                }
            )
        ),
        encoding="utf-8",
    )

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = import_workflow(document)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "Workflow document must declare a result.\n"

    assert SQLiteWorkflowRepository(database).get(WORKFLOW_ID) is None


def test_workflow_show_displays_declared_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteWorkflowRepository(database).save(create_workflow())

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = show_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert f"Result: step {STEP_ID} output answer\n" in captured.out

    lines = captured.out.splitlines()

    assert lines.index(f"Result: step {STEP_ID} output answer") < lines.index("Steps: 1")


def test_workflow_show_marks_previously_stored_workflow_as_undeclared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteWorkflowRepository(database).save(
        create_workflow().model_copy(
            update={
                "result": None,
            }
        )
    )

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = show_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0
    assert "Result: undeclared\n" in captured.out

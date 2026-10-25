"""Tests for step messages and value emission in workflow show."""

from pathlib import Path

import pytest

from azathoth.cli import show_workflow
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowStepSpecification,
)
from tests.cli.test_workflow_import import (
    STEP_ID,
    WORKFLOW_ID,
    configure_database,
    create_workflow,
)


def show_stored_workflow(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    message: str | None,
    emit_values: bool,
) -> str:
    """Store the import test workflow with the given step fields, then show it."""

    database = tmp_path / "azathoth.db"

    workflow = create_workflow()

    step = WorkflowStepSpecification.model_validate(
        {
            **workflow.steps[0].model_dump(),
            "message": message,
            "emit_values": emit_values,
        }
    )

    SQLiteWorkflowRepository(database).save(
        workflow.model_copy(
            update={
                "steps": (step,),
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
    assert captured.err == ""

    return captured.out


def test_workflow_show_displays_step_message_and_value_emission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = show_stored_workflow(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        message="Counting words",
        emit_values=True,
    )

    assert (
        f"ID: {STEP_ID}\n"
        "Type: prompt\n"
        "Strategy: import prompt\n"
        "Message: Counting words\n"
        "Emits values: yes\n"
        "Dependencies: 0\n"
    ) in output


def test_workflow_show_displays_message_without_value_emission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = show_stored_workflow(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        message="Counting words",
        emit_values=False,
    )

    assert "Message: Counting words\n" in output
    assert "Emits values" not in output


def test_workflow_show_omits_presentation_lines_for_silent_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = show_stored_workflow(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        message=None,
        emit_values=False,
    )

    assert "Message:" not in output
    assert "Emits values" not in output

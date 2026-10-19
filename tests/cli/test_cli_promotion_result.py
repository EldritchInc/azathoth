"""Tests for rejecting CLI promotion of workflows without declared results."""

from pathlib import Path

import pytest

from azathoth.cli import main
from azathoth.workflows import (
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
)
from tests.cli.test_workflow_promotion_lifecycle import (
    WORKFLOW_ID,
    configure_cli_runtime,
    create_workflow,
)


def test_cli_promotion_rejects_workflow_without_result(
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

    configure_cli_runtime(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = main(
        (
            "workflow",
            "promote",
            str(WORKFLOW_ID),
        )
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == f"Workflow {WORKFLOW_ID} does not declare a result.\n"

    assert SQLiteWorkflowProductionStateRepository(database).get(WORKFLOW_ID) is None
    assert SQLiteWorkflowProductionRevisionRepository(database).revisions() == ()

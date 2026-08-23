"""Tests for workflow command dispatch through the CLI application."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    main,
)
from azathoth.prompting import PromptStrategySpec
from azathoth.providers import (
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    encode_workflow_document,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNKNOWN_WORKFLOW_ID = UUID("99999999-9999-9999-9999-999999999999")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_workflow() -> WorkflowSpecification:
    """Create one workflow visible through the command-line application."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="application workflow",
            description=("Exercise workflow inspection through CLI dispatch."),
            version="1.2.3",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="application prompt",
                        description="Exercise CLI dispatch.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_requirements=ModelRequirements(),
                ),
            ),
        ),
    )


def configure_workflow(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist and configure one workflow for CLI dispatch tests."""

    SQLiteWorkflowRepository(database).save(create_workflow())

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def test_cli_workflow_list_dispatches_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_workflow(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = main(
        (
            "workflow",
            "list",
        )
    )

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (f"{WORKFLOW_ID}  1.2.3  application workflow\n")

    assert captured.err == ""


def test_cli_workflow_show_dispatches_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_workflow(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = main(
        (
            "workflow",
            "show",
            str(WORKFLOW_ID),
        )
    )

    captured = capsys.readouterr()

    assert result == 0

    assert f"ID: {WORKFLOW_ID}\n" in captured.out

    assert "Name: application workflow\n" in captured.out
    assert "Version: 1.2.3\n" in captured.out

    assert captured.err == ""


def test_cli_workflow_show_returns_nonzero_for_unknown_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "empty.db"

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    result = main(
        (
            "workflow",
            "show",
            str(UNKNOWN_WORKFLOW_ID),
        )
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n")


def test_cli_workflow_show_rejects_invalid_uuid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "show",
                "definitely-not-a-uuid",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 2

    assert captured.out == ""

    assert "invalid UUID value" in captured.err


def test_cli_help_includes_workflow_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--help",))

    captured = capsys.readouterr()

    assert raised.value.code == 0

    assert "workflow" in captured.out


def test_cli_workflow_help_includes_actions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0

    assert "list" in captured.out
    assert "show" in captured.out
    assert "import" in captured.out


def test_cli_workflow_show_help_describes_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "show",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0

    assert "WORKFLOW_ID" in captured.out

    assert "Workflow UUID to inspect." in captured.out


def test_cli_workflow_import_dispatches_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document = tmp_path / "workflow.json"

    document.write_text(
        encode_workflow_document(create_workflow()),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    result = main(
        (
            "workflow",
            "import",
            str(document),
        )
    )

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (f"Imported workflow {WORKFLOW_ID}.\n")

    assert captured.err == ""


def test_cli_workflow_import_help_describes_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            (
                "workflow",
                "import",
                "--help",
            )
        )

    captured = capsys.readouterr()

    assert raised.value.code == 0

    assert "FILE" in captured.out

    assert "JSON workflow document to import." in captured.out

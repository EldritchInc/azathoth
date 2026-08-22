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
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_workflow() -> WorkflowSpecification:
    """Create one workflow visible through the command-line application."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="application workflow",
            description=("Exercise workflow listing through CLI dispatch."),
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


def test_cli_workflow_list_dispatches_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteWorkflowRepository(database).save(create_workflow())

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
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


def test_cli_help_includes_workflow_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(("--help",))

    captured = capsys.readouterr()

    assert raised.value.code == 0

    assert "workflow" in captured.out


def test_cli_workflow_help_includes_list_action(
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

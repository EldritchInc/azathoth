"""Tests for Azathoth CLI workflow commands."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    list_workflows,
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

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

FIRST_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")

SECOND_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")


def create_workflow(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
    version: str,
) -> WorkflowSpecification:
    """Create one durable workflow for CLI inspection."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=name,
            description=(f"Exercise CLI inspection for {name}."),
            version=version,
        ),
        steps=(
            WorkflowStepSpecification(
                id=step_id,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=strategy_id,
                        name=f"{name} prompt",
                        description=(f"Execute the {name} prompt."),
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


def configure_database(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure the CLI to use one deterministic test database."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def test_workflow_list_prints_configured_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    workflow = create_workflow(
        workflow_id=FIRST_WORKFLOW_ID,
        step_id=FIRST_STEP_ID,
        strategy_id=FIRST_STRATEGY_ID,
        name="classify sentiment",
        version="1.0.0",
    )

    SQLiteWorkflowRepository(database).save(workflow)

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = list_workflows()

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (f"{FIRST_WORKFLOW_ID}  1.0.0  classify sentiment\n")

    assert captured.err == ""


def test_workflow_list_preserves_repository_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    repository = SQLiteWorkflowRepository(database)

    repository.save(
        create_workflow(
            workflow_id=SECOND_WORKFLOW_ID,
            step_id=SECOND_STEP_ID,
            strategy_id=SECOND_STRATEGY_ID,
            name="extract invoice",
            version="2.1.0",
        )
    )

    repository.save(
        create_workflow(
            workflow_id=FIRST_WORKFLOW_ID,
            step_id=FIRST_STEP_ID,
            strategy_id=FIRST_STRATEGY_ID,
            name="classify sentiment",
            version="1.0.0",
        )
    )

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = list_workflows()

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (
        f"{SECOND_WORKFLOW_ID}  "
        "2.1.0  "
        "extract invoice\n"
        f"{FIRST_WORKFLOW_ID}  "
        "1.0.0  "
        "classify sentiment\n"
    )


def test_workflow_list_prints_nothing_for_empty_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "empty.db"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = list_workflows()

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_workflow_list_does_not_require_openrouter_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteWorkflowRepository(database).save(
        create_workflow(
            workflow_id=FIRST_WORKFLOW_ID,
            step_id=FIRST_STEP_ID,
            strategy_id=FIRST_STRATEGY_ID,
            name="classify sentiment",
            version="1.0.0",
        )
    )

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    monkeypatch.delenv(
        "OPENROUTER_API_KEY",
        raising=False,
    )

    result = list_workflows()

    captured = capsys.readouterr()

    assert result == 0

    assert "classify sentiment" in captured.out

"""End-to-end tests for installed workflow inspection commands."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli import DATABASE_ENVIRONMENT_VARIABLE
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

UNKNOWN_WORKFLOW_ID = UUID("99999999-9999-9999-9999-999999999999")

FIRST_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

FIRST_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")

SECOND_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")


def console_script() -> Path:
    """Return the installed Azathoth console script."""

    script = Path(sys.executable).with_name("azathoth")

    assert script.exists()

    return script


def create_workflow(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
    description: str,
    version: str,
) -> WorkflowSpecification:
    """Create one durable workflow visible through the installed CLI."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=name,
            description=description,
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


def persist_workflows(
    database: Path,
) -> None:
    """Persist deterministic workflows in repository order."""

    repository = SQLiteWorkflowRepository(database)

    repository.save(
        create_workflow(
            workflow_id=SECOND_WORKFLOW_ID,
            step_id=SECOND_STEP_ID,
            strategy_id=SECOND_STRATEGY_ID,
            name="extract invoice",
            description="Extract fields from one invoice.",
            version="2.1.0",
        )
    )

    repository.save(
        create_workflow(
            workflow_id=FIRST_WORKFLOW_ID,
            step_id=FIRST_STEP_ID,
            strategy_id=FIRST_STRATEGY_ID,
            name="classify sentiment",
            description="Classify sentiment for one request.",
            version="1.0.0",
        )
    )


def cli_environment(
    *,
    database: Path,
) -> dict[str, str]:
    """Return environment for installed workflow CLI execution."""

    environment = os.environ.copy()

    environment[DATABASE_ENVIRONMENT_VARIABLE] = str(database)

    environment.pop(
        "OPENROUTER_API_KEY",
        None,
    )

    return environment


def run_cli(
    *arguments: str,
    database: Path,
) -> subprocess.CompletedProcess[str]:
    """Run one installed Azathoth workflow command."""

    return subprocess.run(
        [
            str(console_script()),
            *arguments,
        ],
        env=cli_environment(database=database),
        check=False,
        capture_output=True,
        text=True,
    )


def test_installed_workflow_list_reads_configured_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_workflows(database)

    result = run_cli(
        "workflow",
        "list",
        database=database,
    )

    assert result.returncode == 0

    assert result.stdout == (
        f"{SECOND_WORKFLOW_ID}  "
        "2.1.0  "
        "extract invoice\n"
        f"{FIRST_WORKFLOW_ID}  "
        "1.0.0  "
        "classify sentiment\n"
    )

    assert result.stderr == ""


def test_installed_workflow_show_reads_durable_metadata(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_workflows(database)

    result = run_cli(
        "workflow",
        "show",
        str(FIRST_WORKFLOW_ID),
        database=database,
    )

    assert result.returncode == 0

    assert f"ID: {FIRST_WORKFLOW_ID}\n" in result.stdout

    assert "Name: classify sentiment\n" in result.stdout

    assert "Version: 1.0.0\n" in result.stdout

    assert "Description: Classify sentiment for one request.\n" in result.stdout

    assert "Steps: 1\n" in result.stdout

    assert f"ID: {FIRST_STEP_ID}\n" in result.stdout

    assert "Type: prompt\n" in result.stdout

    assert "Strategy: classify sentiment prompt\n" in result.stdout

    assert result.stderr == ""


def test_installed_workflow_inspection_requires_no_provider_credentials(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_workflows(database)

    result = run_cli(
        "workflow",
        "list",
        database=database,
    )

    assert result.returncode == 0

    assert "classify sentiment" in result.stdout


def test_installed_workflow_show_returns_nonzero_for_unknown_workflow(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_workflows(database)

    result = run_cli(
        "workflow",
        "show",
        str(UNKNOWN_WORKFLOW_ID),
        database=database,
    )

    assert result.returncode == 1

    assert result.stdout == ""

    assert result.stderr == (f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n")


def test_installed_workflow_show_rejects_invalid_uuid(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_workflows(database)

    result = run_cli(
        "workflow",
        "show",
        "definitely-not-a-uuid",
        database=database,
    )

    assert result.returncode == 2

    assert result.stdout == ""

    assert "invalid UUID value" in result.stderr


def test_installed_workflow_list_handles_empty_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "empty.db"

    result = run_cli(
        "workflow",
        "list",
        database=database,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_installed_workflow_help_does_not_create_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "does-not-exist.db"

    assert not database.exists()

    result = run_cli(
        "workflow",
        "--help",
        database=database,
    )

    assert result.returncode == 0

    assert "list" in result.stdout
    assert "show" in result.stdout

    assert not database.exists()

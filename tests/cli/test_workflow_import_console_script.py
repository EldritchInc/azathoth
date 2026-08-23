"""End-to-end tests for the installed workflow import lifecycle."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
)

PROJECT_ROOT = Path(__file__).parents[2]

SIMPLE_PROMPT_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "simple-prompt.json"

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")


def console_script() -> Path:
    """Return the installed Azathoth console script."""

    script = Path(sys.executable).with_name("azathoth")

    assert script.exists()

    return script


def cli_environment(
    *,
    database: Path,
) -> dict[str, str]:
    """Return environment for one isolated CLI application database."""

    environment = os.environ.copy()

    environment[DATABASE_ENVIRONMENT_VARIABLE] = str(database)

    environment.pop(
        OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
        None,
    )

    return environment


def run_cli(
    *arguments: str,
    database: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the installed Azathoth console script."""

    return subprocess.run(
        [
            str(console_script()),
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        env=cli_environment(database=database),
        check=False,
        capture_output=True,
        text=True,
    )


def test_installed_cli_imports_checked_in_workflow_example(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    result = run_cli(
        "workflow",
        "import",
        str(SIMPLE_PROMPT_DOCUMENT),
        database=database,
    )

    assert result.returncode == 0

    assert result.stdout == (f"Imported workflow {WORKFLOW_ID}.\n")

    assert result.stderr == ""

    assert database.exists()


def test_imported_example_appears_in_installed_workflow_list(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    imported = run_cli(
        "workflow",
        "import",
        str(SIMPLE_PROMPT_DOCUMENT),
        database=database,
    )

    assert imported.returncode == 0

    listed = run_cli(
        "workflow",
        "list",
        database=database,
    )

    assert listed.returncode == 0

    assert listed.stdout == (f"{WORKFLOW_ID}  1.0.0  simple prompt\n")

    assert listed.stderr == ""


def test_imported_example_appears_in_installed_workflow_show(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    imported = run_cli(
        "workflow",
        "import",
        str(SIMPLE_PROMPT_DOCUMENT),
        database=database,
    )

    assert imported.returncode == 0

    shown = run_cli(
        "workflow",
        "show",
        str(WORKFLOW_ID),
        database=database,
    )

    assert shown.returncode == 0

    assert f"ID: {WORKFLOW_ID}\n" in shown.stdout

    assert "Name: simple prompt\n" in shown.stdout
    assert "Version: 1.0.0\n" in shown.stdout

    assert "Description: Return a concise answer to one request.\n" in shown.stdout

    assert "Steps: 1\n" in shown.stdout
    assert "Step 1\n" in shown.stdout

    assert f"ID: {STEP_ID}\n" in shown.stdout

    assert "Type: prompt\n" in shown.stdout
    assert "Strategy: answer request\n" in shown.stdout
    assert "Dependencies: 0\n" in shown.stdout
    assert "Inputs: 0\n" in shown.stdout
    assert "Outputs: 0\n" in shown.stdout
    assert "Conditions: 0\n" in shown.stdout

    assert shown.stderr == ""


def test_installed_workflow_import_lifecycle_requires_no_provider_credentials(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    imported = run_cli(
        "workflow",
        "import",
        str(SIMPLE_PROMPT_DOCUMENT),
        database=database,
    )

    assert imported.returncode == 0

    listed = run_cli(
        "workflow",
        "list",
        database=database,
    )

    shown = run_cli(
        "workflow",
        "show",
        str(WORKFLOW_ID),
        database=database,
    )

    assert listed.returncode == 0
    assert shown.returncode == 0


def test_installed_workflow_import_rejects_duplicate_example(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    first = run_cli(
        "workflow",
        "import",
        str(SIMPLE_PROMPT_DOCUMENT),
        database=database,
    )

    assert first.returncode == 0

    second = run_cli(
        "workflow",
        "import",
        str(SIMPLE_PROMPT_DOCUMENT),
        database=database,
    )

    assert second.returncode == 1

    assert second.stdout == ""

    assert second.stderr == (f"Workflow specification {WORKFLOW_ID} already exists.\n")


def test_installed_workflow_import_rejects_missing_document(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    missing = tmp_path / "missing.json"

    result = run_cli(
        "workflow",
        "import",
        str(missing),
        database=database,
    )

    assert result.returncode == 1

    assert result.stdout == ""

    assert f"Unable to read workflow document {missing}:" in result.stderr

    assert not database.exists()


def test_installed_workflow_import_rejects_invalid_document_without_persistence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"
    document = tmp_path / "invalid.json"

    document.write_text(
        '{"definitely":"not a workflow"}',
        encoding="utf-8",
    )

    result = run_cli(
        "workflow",
        "import",
        str(document),
        database=database,
    )

    assert result.returncode == 1

    assert result.stdout == ""

    assert result.stderr == ("Workflow document is not a valid WorkflowSpecification.\n")

    assert not database.exists()


def test_installed_workflow_import_list_show_lifecycle(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    imported = run_cli(
        "workflow",
        "import",
        str(SIMPLE_PROMPT_DOCUMENT),
        database=database,
    )

    assert imported.returncode == 0

    listed = run_cli(
        "workflow",
        "list",
        database=database,
    )

    assert listed.returncode == 0

    shown = run_cli(
        "workflow",
        "show",
        str(WORKFLOW_ID),
        database=database,
    )

    assert shown.returncode == 0

    assert imported.stdout == (f"Imported workflow {WORKFLOW_ID}.\n")

    assert listed.stdout == (f"{WORKFLOW_ID}  1.0.0  simple prompt\n")

    assert "Name: simple prompt\n" in shown.stdout

    assert "Strategy: answer request\n" in shown.stdout

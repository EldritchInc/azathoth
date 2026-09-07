"""End-to-end tests for the installed tool CLI lifecycle."""

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

WORD_COUNT_DOCUMENT = PROJECT_ROOT / "examples" / "tools" / "word-count.json"

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_TEST_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_TEST_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")


def console_script() -> Path:
    """Return the installed Azathoth console script."""

    script = Path(sys.executable).with_name(
        "azathoth",
    )

    assert script.exists()

    return script


def cli_environment(
    *,
    database: Path,
) -> dict[str, str]:
    """Return environment for one isolated CLI database."""

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
        env=cli_environment(
            database=database,
        ),
        check=False,
        capture_output=True,
        text=True,
    )


def import_example(
    database: Path,
) -> subprocess.CompletedProcess[str]:
    """Import the checked-in word-count example."""

    return run_cli(
        "tool",
        "import",
        str(WORD_COUNT_DOCUMENT),
        database=database,
    )


def test_installed_cli_imports_checked_in_tool_example(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    result = import_example(
        database,
    )

    assert result.returncode == 0

    assert result.stdout == (f"Imported tool {TOOL_ID}@1.0.0.\n")

    assert result.stderr == ""
    assert database.exists()


def test_installed_cli_lists_imported_tool(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert import_example(database).returncode == 0

    result = run_cli(
        "tool",
        "list",
        database=database,
    )

    assert result.returncode == 0

    assert result.stdout == (f"{TOOL_ID}  1.0.0  word_count\n")

    assert result.stderr == ""


def test_installed_cli_lists_imported_tool_versions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert import_example(database).returncode == 0

    result = run_cli(
        "tool",
        "versions",
        str(TOOL_ID),
        database=database,
    )

    assert result.returncode == 0
    assert result.stdout == "1.0.0\n"
    assert result.stderr == ""


def test_installed_cli_shows_imported_tool(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert import_example(database).returncode == 0

    result = run_cli(
        "tool",
        "show",
        str(TOOL_ID),
        "--version",
        "1.0.0",
        database=database,
    )

    assert result.returncode == 0
    assert f"ID: {TOOL_ID}\n" in result.stdout
    assert "Name: word_count\n" in result.stdout
    assert "Version: 1.0.0\n" in result.stdout
    assert "Input Schema:\n" in result.stdout
    assert "Output Schema:\n" in result.stdout
    assert result.stderr == ""


def test_installed_cli_lists_imported_implementations(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert import_example(database).returncode == 0

    result = run_cli(
        "tool",
        "implementations",
        str(TOOL_ID),
        "--version",
        "1.0.0",
        database=database,
    )

    assert result.returncode == 0

    assert result.stdout == (f"{IMPLEMENTATION_ID}  1.0.0  python\n")

    assert result.stderr == ""


def test_installed_cli_shows_imported_implementation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert import_example(database).returncode == 0

    result = run_cli(
        "tool",
        "implementation-show",
        str(IMPLEMENTATION_ID),
        database=database,
    )

    assert result.returncode == 0

    assert f"ID: {IMPLEMENTATION_ID}\n" in result.stdout

    assert f"Tool ID: {TOOL_ID}\n" in result.stdout
    assert "Tool Version: 1.0.0\n" in result.stdout
    assert "Implementation Version: 1.0.0\n" in result.stdout
    assert "Runtime: python\n" in result.stdout
    assert "Entrypoint: run\n" in result.stdout
    assert "Source:\n" in result.stdout
    assert result.stderr == ""


def test_installed_cli_lists_imported_test_cases(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert import_example(database).returncode == 0

    result = run_cli(
        "tool",
        "test-cases",
        str(TOOL_ID),
        database=database,
    )

    assert result.returncode == 0

    assert result.stdout == (
        f"{FIRST_TEST_CASE_ID}  counts two words\n{SECOND_TEST_CASE_ID}  counts empty input\n"
    )

    assert result.stderr == ""


def test_installed_cli_shows_imported_test_case(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert import_example(database).returncode == 0

    result = run_cli(
        "tool",
        "test-case-show",
        str(FIRST_TEST_CASE_ID),
        database=database,
    )

    assert result.returncode == 0

    assert f"ID: {FIRST_TEST_CASE_ID}\n" in result.stdout

    assert f"Tool ID: {TOOL_ID}\n" in result.stdout
    assert "Name: counts two words\n" in result.stdout
    assert "Inputs:\n" in result.stdout
    assert "Expected Output:\n" in result.stdout
    assert result.stderr == ""


def test_installed_cli_verifies_imported_tool(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert import_example(database).returncode == 0

    result = run_cli(
        "tool",
        "verify",
        str(TOOL_ID),
        "--version",
        "1.0.0",
        database=database,
    )

    assert result.returncode == 0
    assert result.stderr == ""

    assert f"Implementation ID: {IMPLEMENTATION_ID}" in result.stdout

    assert "Implementation Version: 1.0.0" in result.stdout
    assert "Runtime: python" in result.stdout
    assert "Status: passed" in result.stdout
    assert "Tests: 2" in result.stdout
    assert "Passed: 2" in result.stdout
    assert "Failed: 0" in result.stdout
    assert "Pass Rate: 1.000000" in result.stdout

    assert f"  Test Case ID: {FIRST_TEST_CASE_ID}" in result.stdout

    assert f"  Test Case ID: {SECOND_TEST_CASE_ID}" in result.stdout

"""End-to-end tests for the installed Azathoth console application."""

import os
import subprocess
import sys
from pathlib import Path

from azathoth import __version__
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
)


def console_script() -> Path:
    """Return the console script installed beside the active Python executable."""

    executable = Path(sys.executable)

    script = executable.with_name("azathoth")

    assert script.exists()

    return script


def clean_environment() -> dict[str, str]:
    """Return process environment without Azathoth runtime configuration."""

    environment = os.environ.copy()

    environment.pop(
        DATABASE_ENVIRONMENT_VARIABLE,
        None,
    )

    environment.pop(
        OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
        None,
    )

    return environment


def run_cli(
    *arguments: str,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the installed Azathoth console script."""

    return subprocess.run(
        [
            str(console_script()),
            *arguments,
        ],
        cwd=cwd,
        env=(environment if environment is not None else clean_environment()),
        check=False,
        capture_output=True,
        text=True,
    )


def test_installed_cli_without_arguments_displays_help(
    tmp_path: Path,
) -> None:
    result = run_cli(
        cwd=tmp_path,
    )

    assert result.returncode == 0

    assert result.stdout.startswith("usage: azathoth")

    assert "Empirical optimization for context-aware AI workflows." in result.stdout

    assert result.stderr == ""


def test_installed_cli_help_exits_successfully(
    tmp_path: Path,
) -> None:
    result = run_cli(
        "--help",
        cwd=tmp_path,
    )

    assert result.returncode == 0

    assert result.stdout.startswith("usage: azathoth")

    assert "--version" in result.stdout

    assert result.stderr == ""


def test_installed_cli_version_matches_package_version(
    tmp_path: Path,
) -> None:
    result = run_cli(
        "--version",
        cwd=tmp_path,
    )

    assert result.returncode == 0

    assert result.stdout == (f"azathoth {__version__}\n")

    assert result.stderr == ""


def test_installed_cli_rejects_unknown_arguments(
    tmp_path: Path,
) -> None:
    result = run_cli(
        "--definitely-not-an-option",
        cwd=tmp_path,
    )

    assert result.returncode == 2

    assert result.stdout == ""

    assert "usage: azathoth" in result.stderr

    assert "unrecognized arguments: --definitely-not-an-option" in result.stderr


def test_installed_cli_shell_does_not_create_default_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert not database.exists()

    result = run_cli(
        cwd=tmp_path,
    )

    assert result.returncode == 0

    assert not database.exists()


def test_installed_cli_help_does_not_bootstrap_runtime(
    tmp_path: Path,
) -> None:
    database = tmp_path / "configured.db"

    environment = clean_environment()

    environment[DATABASE_ENVIRONMENT_VARIABLE] = str(database)

    environment[OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE] = "test-secret-that-must-not-be-used"

    result = run_cli(
        "--help",
        cwd=tmp_path,
        environment=environment,
    )

    assert result.returncode == 0

    assert not database.exists()


def test_installed_cli_version_does_not_bootstrap_runtime(
    tmp_path: Path,
) -> None:
    database = tmp_path / "configured.db"

    environment = clean_environment()

    environment[DATABASE_ENVIRONMENT_VARIABLE] = str(database)

    environment[OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE] = "test-secret-that-must-not-be-used"

    result = run_cli(
        "--version",
        cwd=tmp_path,
        environment=environment,
    )

    assert result.returncode == 0

    assert result.stdout == (f"azathoth {__version__}\n")

    assert not database.exists()


def test_installed_cli_console_script_uses_current_environment(
    tmp_path: Path,
) -> None:
    script = console_script()

    assert script.parent == Path(sys.executable).parent

    result = run_cli(
        "--version",
        cwd=tmp_path,
    )

    assert result.returncode == 0

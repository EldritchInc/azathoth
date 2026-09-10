"""End-to-end smoke tests for installed benchmark execution commands."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
)

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")


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
    """Return an isolated environment for installed CLI execution."""

    environment = os.environ.copy()

    environment[DATABASE_ENVIRONMENT_VARIABLE] = str(database)

    environment.pop(
        OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
        None,
    )

    return environment


def run_cli(
    *arguments: str,
    cwd: Path,
    database: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the installed Azathoth console script."""

    return subprocess.run(
        [
            str(console_script()),
            *arguments,
        ],
        cwd=cwd,
        env=cli_environment(
            database=database,
        ),
        check=False,
        capture_output=True,
        text=True,
    )


def test_installed_benchmark_help_exposes_execution_commands(
    tmp_path: Path,
) -> None:
    result = run_cli(
        "benchmark",
        "--help",
        cwd=tmp_path,
        database=tmp_path / "azathoth.db",
    )

    assert result.returncode == 0
    assert "run" in result.stdout
    assert "compare" in result.stdout
    assert result.stderr == ""


def test_installed_benchmark_run_help_exposes_execution_arguments(
    tmp_path: Path,
) -> None:
    result = run_cli(
        "benchmark",
        "run",
        "--help",
        cwd=tmp_path,
        database=tmp_path / "azathoth.db",
    )

    assert result.returncode == 0

    assert "BENCHMARK_ID" in result.stdout
    assert "--workflow" in result.stdout
    assert "WORKFLOW_ID" in result.stdout
    assert "--output" in result.stdout
    assert "OUTPUT" in result.stdout

    assert result.stderr == ""


def test_installed_benchmark_compare_help_exposes_scoring_arguments(
    tmp_path: Path,
) -> None:
    result = run_cli(
        "benchmark",
        "compare",
        "--help",
        cwd=tmp_path,
        database=tmp_path / "azathoth.db",
    )

    assert result.returncode == 0

    assert "BENCHMARK_ID" in result.stdout
    assert "--workflow" in result.stdout
    assert "WORKFLOW_ID" in result.stdout
    assert "--output" in result.stdout
    assert "OUTPUT" in result.stdout
    assert "--target-latency" in result.stdout
    assert "SECONDS" in result.stdout
    assert "--target-cost" in result.stdout
    assert "USD" in result.stdout

    assert result.stderr == ""


def test_installed_benchmark_run_reaches_operator_command(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    result = run_cli(
        "benchmark",
        "run",
        str(BENCHMARK_ID),
        "--workflow",
        str(FIRST_WORKFLOW_ID),
        "--output",
        "classification",
        cwd=tmp_path,
        database=database,
    )

    assert result.returncode == 1
    assert result.stdout == ""

    assert result.stderr == (f"Benchmark dataset {BENCHMARK_ID} is not configured.\n")

    assert "Traceback" not in result.stderr


def test_installed_benchmark_compare_reaches_operator_command(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    result = run_cli(
        "benchmark",
        "compare",
        str(BENCHMARK_ID),
        "--workflow",
        str(FIRST_WORKFLOW_ID),
        "--workflow",
        str(SECOND_WORKFLOW_ID),
        "--output",
        "classification",
        "--target-latency",
        "5",
        "--target-cost",
        "0.001",
        cwd=tmp_path,
        database=database,
    )

    assert result.returncode == 1
    assert result.stdout == ""

    assert result.stderr == (f"Benchmark dataset {BENCHMARK_ID} is not configured.\n")

    assert "Traceback" not in result.stderr

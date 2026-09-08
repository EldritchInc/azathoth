"""End-to-end tests for installed benchmark and goal configuration."""

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

BENCHMARK_DOCUMENT = PROJECT_ROOT / "examples" / "benchmarks" / "classification.json"

GOAL_DOCUMENT = PROJECT_ROOT / "examples" / "goals" / "accurate-answer.json"

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

POSITIVE_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")

NEGATIVE_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

GOAL_ID = UUID("44444444-4444-4444-4444-444444444444")


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


def import_benchmark(
    database: Path,
) -> subprocess.CompletedProcess[str]:
    """Import the checked-in benchmark example."""

    return run_cli(
        "benchmark",
        "import",
        str(BENCHMARK_DOCUMENT),
        database=database,
    )


def import_goal(
    database: Path,
) -> subprocess.CompletedProcess[str]:
    """Import the checked-in goal example."""

    return run_cli(
        "goal",
        "import",
        str(GOAL_DOCUMENT),
        database=database,
    )


def test_installed_cli_imports_checked_in_benchmark(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    result = import_benchmark(
        database,
    )

    assert result.returncode == 0

    assert result.stdout == (f"Imported benchmark dataset {BENCHMARK_ID}.\n")

    assert result.stderr == ""
    assert database.exists()


def test_installed_cli_lists_imported_benchmark(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert (
        import_benchmark(
            database,
        ).returncode
        == 0
    )

    result = run_cli(
        "benchmark",
        "list",
        database=database,
    )

    assert result.returncode == 0

    assert result.stdout == (f"{BENCHMARK_ID}  1.0.0  classification benchmark\n")

    assert result.stderr == ""


def test_installed_cli_shows_imported_benchmark(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert (
        import_benchmark(
            database,
        ).returncode
        == 0
    )

    result = run_cli(
        "benchmark",
        "show",
        str(BENCHMARK_ID),
        database=database,
    )

    assert result.returncode == 0
    assert result.stderr == ""

    assert f"ID: {BENCHMARK_ID}\n" in result.stdout
    assert "Name: classification benchmark\n" in result.stdout
    assert "Version: 1.0.0\n" in result.stdout
    assert "Cases: 2\n" in result.stdout


def test_installed_cli_lists_imported_benchmark_cases(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert (
        import_benchmark(
            database,
        ).returncode
        == 0
    )

    result = run_cli(
        "benchmark",
        "cases",
        str(BENCHMARK_ID),
        database=database,
    )

    assert result.returncode == 0

    assert result.stdout == (
        f"{POSITIVE_CASE_ID}  Classify the input as positive.\n"
        f"{NEGATIVE_CASE_ID}  Classify the input as negative.\n"
    )

    assert result.stderr == ""


def test_installed_cli_shows_imported_benchmark_case(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert (
        import_benchmark(
            database,
        ).returncode
        == 0
    )

    result = run_cli(
        "benchmark",
        "case-show",
        str(BENCHMARK_ID),
        str(POSITIVE_CASE_ID),
        database=database,
    )

    assert result.returncode == 0
    assert result.stderr == ""

    assert f"ID: {POSITIVE_CASE_ID}\n" in result.stdout
    assert "Input:\n" in result.stdout
    assert '"This was excellent."' in result.stdout
    assert "Expected:\n" in result.stdout
    assert "  Description: Classify the input as positive.\n" in result.stdout
    assert "  Comparison: exact\n" in result.stdout
    assert '    "positive"' in result.stdout
    assert "Metadata:\n" in result.stdout


def test_installed_cli_imports_checked_in_goal(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    result = import_goal(
        database,
    )

    assert result.returncode == 0

    assert result.stdout == (f"Imported goal {GOAL_ID}.\n")

    assert result.stderr == ""
    assert database.exists()


def test_installed_cli_lists_imported_goal(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert (
        import_goal(
            database,
        ).returncode
        == 0
    )

    result = run_cli(
        "goal",
        "list",
        database=database,
    )

    assert result.returncode == 0

    assert result.stdout == (f"{GOAL_ID}  Answer accurately\n")

    assert result.stderr == ""


def test_installed_cli_shows_imported_goal(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    assert (
        import_goal(
            database,
        ).returncode
        == 0
    )

    result = run_cli(
        "goal",
        "show",
        str(GOAL_ID),
        database=database,
    )

    assert result.returncode == 0
    assert result.stderr == ""

    assert f"ID: {GOAL_ID}\n" in result.stdout
    assert "Name: Answer accurately\n" in result.stdout

    assert "Description: Produce the correct answer for the supplied request.\n" in result.stdout

    assert "Success Criteria:\n" in result.stdout

    assert "  - The answer matches the expected result.\n" in result.stdout

    assert "  - The answer remains factual.\n" in result.stdout

    assert "Constraints:\n" in result.stdout

    assert "  - Do not rely on unavailable external state.\n" in result.stdout

    assert "  - Remain provider independent.\n" in result.stdout


def test_installed_cli_imports_benchmark_and_goal_into_same_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    benchmark_result = import_benchmark(
        database,
    )

    goal_result = import_goal(
        database,
    )

    assert benchmark_result.returncode == 0
    assert goal_result.returncode == 0

    benchmark_list = run_cli(
        "benchmark",
        "list",
        database=database,
    )

    goal_list = run_cli(
        "goal",
        "list",
        database=database,
    )

    assert benchmark_list.returncode == 0
    assert goal_list.returncode == 0

    assert str(BENCHMARK_ID) in benchmark_list.stdout
    assert str(GOAL_ID) in goal_list.stdout

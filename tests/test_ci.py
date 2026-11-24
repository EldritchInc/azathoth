"""Tests that CI runs the suite where it must, and not twice.

A pull request runs the suite on Linux with every Python Azathoth supports,
and on macOS and Windows with the newest; a push to `main` runs it on every
platform with every Python, the nine jobs a release is tagged after. The
`quality` job lints, formats and type-checks, and leaves the tests to the
matrix. The matrix runs the suite in parallel, one worker for each core;
the PostgreSQL and image tests, which share a database and an image, run
one at a time. The workflow is read as text, as the other workflow tests
read it.
"""

import itertools
import re
import tomllib
from pathlib import Path

from tests.container.test_workflows import job

PROJECT_ROOT = Path(__file__).parents[1]

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

RELEASE_VALIDATION = PROJECT_ROOT / "docs" / "release-validation.md"

PARALLEL = "pytest-xdist>=3.6,<4"

PLATFORMS = ("ubuntu-latest", "macos-latest", "windows-latest")

PYTHONS = ("3.11", "3.12", "3.13")

NEWEST = PYTHONS[-1]


def listed(
    body: str,
    key: str,
) -> tuple[str, ...]:
    """Return the values one matrix key lists, in order."""

    found = re.search(rf"^        {key}:\n(?P<values>(?:          - .*\n)+)", body, re.MULTILINE)

    assert found is not None, key

    return tuple(
        value.strip().removeprefix("- ").strip('"') for value in found.group("values").splitlines()
    )


def excluded(
    body: str,
    event: str,
) -> set[tuple[str, str]]:
    """Return the platforms and Pythons the matrix leaves out for one event."""

    entries = re.findall(
        r"          - os: \$\{\{ github\.event_name == '(?P<event>[a-z_]+)' && "
        r"'(?P<os>[a-z-]+)' \|\| 'none' \}\}\n"
        r"            python-version: \"(?P<python>[0-9.]+)\"\n",
        body,
    )

    return {(os, python) for each, os, python in entries if each == event}


def jobs(
    event: str,
) -> set[tuple[str, str]]:
    """Return the platforms and Pythons the suite runs on for one event."""

    tests = job("ci.yml", "tests")
    every = set(itertools.product(listed(tests, "os"), listed(tests, "python-version")))

    return every - excluded(tests, event)


def test_ci_runs_on_pull_requests_and_on_pushes_to_main() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.startswith(
        "name: CI\n\non:\n  push:\n    branches:\n      - main\n  pull_request:\n"
    )


def test_the_matrix_names_every_platform_and_python() -> None:
    tests = job("ci.yml", "tests")

    assert listed(tests, "os") == PLATFORMS
    assert listed(tests, "python-version") == PYTHONS


def test_a_push_to_main_runs_all_nine_jobs() -> None:
    assert jobs("push") == set(itertools.product(PLATFORMS, PYTHONS))
    assert len(jobs("push")) == 9


def test_a_pull_request_runs_linux_on_every_python_and_the_others_on_the_newest() -> None:
    assert jobs("pull_request") == {
        ("ubuntu-latest", "3.11"),
        ("ubuntu-latest", "3.12"),
        ("ubuntu-latest", "3.13"),
        ("macos-latest", NEWEST),
        ("windows-latest", NEWEST),
    }


def test_nothing_is_left_out_but_for_pull_requests() -> None:
    tests = job("ci.yml", "tests")

    assert tests.count("github.event_name == 'pull_request'") == 4
    assert "github.event_name ==" not in tests.replace("github.event_name == 'pull_request'", "")


def test_windows_has_longer_and_every_run_names_its_slowest_tests() -> None:
    tests = job("ci.yml", "tests")

    assert "    timeout-minutes: ${{ matrix.os == 'windows-latest' && 45 || 30 }}\n" in tests
    assert "        run: python -m pytest -n auto --durations=25\n" in tests


def test_the_matrix_runs_the_suite_in_parallel_and_development_installs_what_does() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert PARALLEL in project["project"]["optional-dependencies"]["dev"]
    assert "-n auto" in job("ci.yml", "tests")


def test_the_postgresql_and_image_tests_run_one_at_a_time() -> None:
    for name in ("postgres", "container"):
        assert " -n " not in job("ci.yml", name), name


def test_the_quality_job_leaves_the_tests_to_the_matrix() -> None:
    quality = job("ci.yml", "quality")

    assert "run: ruff check ." in quality
    assert "run: ruff format --check ." in quality
    assert "run: mypy src/azathoth packages/azathoth-mcp/src/azathoth_mcp tests" in quality
    assert "pytest" not in quality


def test_release_validation_says_which_jobs_run_and_which_must_be_green() -> None:
    validation = " ".join(RELEASE_VALIDATION.read_text(encoding="utf-8").split())

    assert (
        "A pull request runs the test suite on Linux with Python 3.11, 3.12 and 3.13, and "
        "on macOS and Windows with Python 3.13." in validation
    )
    assert (
        "A push to `main` runs it on all three with all three Pythons. All nine test jobs "
        "must be green on the commit a release is tagged from." in validation
    )

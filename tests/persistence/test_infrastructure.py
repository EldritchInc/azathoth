"""Tests that PostgreSQL support is installable and tested everywhere it should be (ADR 0102)."""

import re
import tomllib
from pathlib import Path

from tests.container.test_workflows import job
from tests.persistence.conftest import POSTGRES_URL_VARIABLE

PROJECT_ROOT = Path(__file__).parents[2]

DRIVER = "psycopg[binary]>=3.2,<4"


def optional_dependencies() -> dict[str, list[str]]:
    """Return the project's extras."""

    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]

    assert isinstance(extras, dict)

    return extras


def test_the_postgres_extra_installs_psycopg_and_nothing_else() -> None:
    assert optional_dependencies()["postgres"] == [DRIVER]


def test_development_installs_psycopg_too() -> None:
    assert DRIVER in optional_dependencies()["dev"]


def test_psycopg_is_never_a_runtime_dependency() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert not any("psycopg" in requirement for requirement in project["project"]["dependencies"])


def test_ci_runs_the_persistence_tests_against_postgresql() -> None:
    postgres = job("ci.yml", "postgres")

    assert "image: postgres:17" in postgres
    assert "--health-cmd" in postgres
    assert f"{POSTGRES_URL_VARIABLE}: postgresql://" in postgres
    assert "run: python -m pytest tests/persistence -ra" in postgres


def test_the_test_matrix_never_needs_postgresql() -> None:
    assert POSTGRES_URL_VARIABLE not in job("ci.yml", "tests")


def test_make_runs_the_postgresql_tests_against_a_throwaway_server() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    assert re.search(r"^\.PHONY:.*\bpostgres-test\b", makefile, re.MULTILINE)
    assert re.search(r"^postgres-test:$", makefile, re.MULTILINE)
    assert "postgres:17" in makefile
    assert f"{POSTGRES_URL_VARIABLE}=$(POSTGRES_TEST_URL) python -m pytest tests/persistence" in (
        makefile
    )
    assert "docker stop $(POSTGRES_TEST_CONTAINER)" in makefile

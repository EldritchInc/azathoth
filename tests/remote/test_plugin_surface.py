"""Tests that what a remote's plugin may build on is there, and documented (ADR 0134).

Within 1.x a plugin may rely on the names below. Removing or renaming one
fails this test before it fails a plugin, and each is named in the remote's
README, under Writing a Plugin, so a plugin's author knows it is promised.
"""

import importlib
from pathlib import Path

import pytest

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.persistence import (
    DATABASE_VARIABLE,
    DEFAULT_DATABASE,
    PostgresLocation,
    SQLiteLocation,
    database_location,
    run_backfills,
)
from azathoth.persistence import database as database_module

README = Path(__file__).parents[2] / "src" / "azathoth" / "remote" / "README.md"

SURFACE = {
    "azathoth.remote.seams": (
        "Action",
        "AuditEvent",
        "AuditEventKind",
        "AuditSink",
        "Authenticator",
        "Decision",
        "HIGH_PRIVILEGE_ACTIONS",
        "Policy",
        "Principal",
        "RemotePluginError",
    ),
    "azathoth.api.calls": (
        "SERVICE_CALLS",
        "ServiceCall",
        "service_call",
    ),
    "azathoth.persistence": (
        "Database",
        "Dialect",
        "InitializationOutcome",
        "IntegrityError",
        "Parameter",
        "Row",
        "Session",
        "Table",
        "database_location",
        "open_database",
        "require_integer",
        "require_text",
        "run_backfills",
    ),
    "azathoth.persistence.repositories": (
        "open_repositories",
        "postgres_database",
    ),
    "azathoth.remote.tokens": (
        "TOKEN_PREFIX",
        "RemoteToken",
        "RemoteTokenRepository",
    ),
    "azathoth.revisions": (
        "Author",
        "AuthorError",
        "resolve_author",
    ),
}
"""What a plugin may import, module by module, stable within 1.x."""


def writing_a_plugin() -> str:
    """Return the README's Writing a Plugin section."""

    return (
        README.read_text(encoding="utf-8").split("\n### Writing a Plugin\n", 1)[1].split("\n## ")[0]
    )


@pytest.mark.parametrize(("module", "names"), list(SURFACE.items()))
def test_every_name_a_plugin_may_rely_on_is_there(
    module: str,
    names: tuple[str, ...],
) -> None:
    imported = importlib.import_module(module)

    assert [name for name in names if not hasattr(imported, name)] == []
    assert [name for name in names if name not in imported.__all__] == []


def test_every_name_a_plugin_may_rely_on_is_documented() -> None:
    section = writing_a_plugin()

    assert [module for module in SURFACE if f"`{module}`" not in section] == []
    assert [
        name for names in SURFACE.values() for name in names if f"`{name}`" not in section
    ] == []


# Finding the database as the command line does


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {DATABASE_VARIABLE: ""},
        {DATABASE_VARIABLE: "remote.db"},
        {DATABASE_VARIABLE: "/srv/azathoth/remote.db"},
        {DATABASE_VARIABLE: "postgresql://azathoth@db.internal:5432/azathoth"},
    ],
)
def test_a_plugin_finds_the_database_the_command_line_does(
    environment: dict[str, str],
) -> None:
    assert database_location(environment) == (
        CliRuntimeConfiguration.from_environment(environment).location
    )


def test_without_azathoth_database_it_is_azathoth_db_in_the_working_directory() -> None:
    assert DATABASE_VARIABLE == "AZATHOTH_DATABASE"
    assert Path("azathoth.db") == DEFAULT_DATABASE
    assert database_location({}) == SQLiteLocation(path=Path("azathoth.db"))
    assert database_location({DATABASE_VARIABLE: ""}) == SQLiteLocation(path=Path("azathoth.db"))


def test_a_postgresql_url_names_a_postgresql_database() -> None:
    url = "postgresql://azathoth@db.internal:5432/azathoth"

    assert database_location({DATABASE_VARIABLE: url}) == PostgresLocation(url=url)


def test_the_process_environment_is_read_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_VARIABLE, "elsewhere.db")

    assert database_location() == SQLiteLocation(path=Path("elsewhere.db"))


def test_backfills_are_run_as_the_core_runs_them() -> None:
    assert run_backfills is database_module.run_backfills

"""Contract tests for initializing a database through the service API (ADR 0120)."""

import uuid
from pathlib import Path

import pytest

from azathoth import api
from azathoth.persistence import MISSING_DRIVER_MESSAGE, DatabaseUnavailableError
from azathoth.persistence.postgres import PostgresDriver
from azathoth.standard import standard_tool_documents


def test_a_new_sqlite_file_is_created_with_the_standard_tools(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "azathoth.db"

    initialization = api.initialize(path)

    assert initialization.database == str(path.absolute())
    assert initialization.outcome == "created"
    assert path.is_file()
    assert tuple((tool.name, tool.version) for tool in initialization.tools) == tuple(
        (document.definition.name, document.definition.version)
        for document in standard_tool_documents()
    )
    assert all(tool.installed and tool.revision == 1 for tool in initialization.tools)

    with api.open(path) as instance:
        assert len(instance.tools.list()) == len(initialization.tools)


def test_initializing_again_changes_nothing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    api.initialize(path)

    again = api.initialize(path)

    assert again.outcome == "current"
    assert not any(tool.installed for tool in again.tools)
    assert all(tool.revision == 1 for tool in again.tools)


def test_a_changed_standard_tool_is_installed_again_as_its_next_revision(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    api.initialize(path)
    first = standard_tool_documents()[0]

    with api.open(path) as instance:
        changed = instance.tools.get(first.definition.id, first.definition.version).document
        definition = changed["definition"]

        assert isinstance(definition, dict)

        definition["description"] = "An operator's copy."
        instance.tools.import_document(changed)

    again = api.initialize(path)

    assert (again.tools[0].installed, again.tools[0].revision) == (True, 3)
    assert not any(tool.installed for tool in again.tools[1:])


def test_an_initialized_postgresql_database_opens(
    empty_postgres_url: str,
) -> None:
    initialization = api.initialize(empty_postgres_url)

    assert initialization.outcome == "created"
    assert ":azathoth@" not in initialization.database
    assert api.initialize(empty_postgres_url).outcome == "current"

    with api.open(empty_postgres_url) as instance:
        assert len(instance.tools.list()) == len(initialization.tools)


def test_postgresql_without_its_driver_is_not_initialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_driver() -> PostgresDriver:
        raise DatabaseUnavailableError()

    monkeypatch.setattr("azathoth.persistence.postgres.psycopg_driver", no_driver)

    with pytest.raises(api.InstanceUnavailableError) as raised:
        api.initialize(f"postgresql://azathoth@127.0.0.1:1/{uuid.uuid4().hex}")

    assert str(raised.value) == MISSING_DRIVER_MESSAGE


def test_an_sqlite_file_that_cannot_be_made_is_reported(
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    path = blocker / "azathoth.db"

    with pytest.raises(api.InstanceUnavailableError) as raised:
        api.initialize(path)

    assert str(raised.value).startswith(f"Unable to open database {path.absolute()}: ")

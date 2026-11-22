"""Tests of installing the standard tool library through the service API (ADRs 0095 and 0127)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from azathoth import api
from azathoth.api.errors import ConflictError
from azathoth.api.models import StandardTool
from azathoth.api.standard_tools import install_standard_tools
from azathoth.persistence.repositories import open_repositories
from azathoth.revisions import content_digest
from azathoth.standard import STANDARD_TOOL_AUTHOR, standard_tool_documents
from azathoth.tools import InMemoryToolRepository

NAMES = [document.definition.name for document in standard_tool_documents()]


@pytest.fixture
def instance(
    tmp_path: Path,
) -> Iterator[api.Azathoth]:
    path = tmp_path / "azathoth.db"
    sqlite3.connect(path).close()

    with api.open(str(path), author="Eris") as opened:
        yield opened


def test_installing_imports_every_standard_tool_as_its_first_revision(
    instance: api.Azathoth,
) -> None:
    installed = instance.tools.install_standard()

    assert [tool.name for tool in installed] == NAMES
    assert all(tool.installed and tool.revision == 1 for tool in installed)
    assert all(tool.identical_to is None for tool in installed)


def test_installing_again_changes_nothing(
    instance: api.Azathoth,
) -> None:
    instance.tools.install_standard()
    again = instance.tools.install_standard()

    assert not any(tool.installed for tool in again)
    assert [tool.revision for tool in again] == [1] * len(NAMES)


def test_the_standard_tools_are_recorded_as_azathoths_not_the_installers(
    instance: api.Azathoth,
) -> None:
    instance.tools.install_standard()
    (first, *_) = standard_tool_documents()
    tool = instance.tools.get(first.definition.id, first.definition.version)

    assert tool.revision.author is not None
    assert tool.revision.author.name == STANDARD_TOOL_AUTHOR.name == "Azathoth"


def test_a_modified_standard_tool_gets_the_standard_document_back_as_its_next_revision() -> None:
    repository = InMemoryToolRepository()
    install_standard_tools(repository)
    (first, *_) = standard_tool_documents()
    modified = first.model_copy(
        update={"definition": first.definition.model_copy(update={"description": "Changed here."})}
    )
    repository.save_document(modified)

    (restored, *rest) = install_standard_tools(repository)

    assert (restored.installed, restored.revision, restored.identical_to) == (True, 3, 1)
    assert not any(tool.installed for tool in rest)
    latest = repository.latest_document_revision(first.definition.id, first.definition.version)
    assert latest is not None
    assert latest.content_digest == content_digest(first)


def test_each_tool_is_told_as_it_is_installed() -> None:
    told: list[StandardTool] = []
    installed = install_standard_tools(InMemoryToolRepository(), each=told.append)

    assert tuple(told) == installed


def test_a_standard_tool_whose_artifacts_belong_to_another_is_a_conflict() -> None:
    repository = InMemoryToolRepository()
    (first, *_) = standard_tool_documents()
    (implementation, *_) = first.implementations
    other = UUID("c1100000-0000-4000-8000-000000000001")
    clash = first.model_copy(
        update={
            "definition": first.definition.model_copy(update={"id": other, "name": "clash"}),
            "implementations": (implementation.model_copy(update={"tool_id": other}),),
            "test_cases": (),
        }
    )
    repository.save_document(clash)
    told: list[StandardTool] = []

    with pytest.raises(ConflictError):
        install_standard_tools(repository, each=told.append)

    assert told == []


def test_initializing_installs_them_the_same_way(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    initialized = api.initialize(str(path))
    installed = install_standard_tools(open_repositories(path).tools)

    assert [tool.name for tool in initialized.tools] == NAMES
    assert all(tool.installed for tool in initialized.tools)
    assert not any(tool.installed for tool in installed)

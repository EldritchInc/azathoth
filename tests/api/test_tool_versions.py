"""Contract tests for listing a tool's versions (ADR 0133)."""

from pathlib import Path

import pytest

from azathoth import api
from azathoth.cli import list_tool_versions
from azathoth.persistence.repositories import open_repositories
from tests.api.test_browse import (
    MISSING_ID,
    TOOL_ID,
    TOOL_VERSION,
    described_tool,
    example_tool,
    parses,
    versioned_tool,
)
from tests.cli.test_experiment_commands import configure_database


def stock_versions(location: str) -> None:
    """Import the example tool at 1.0.0, twice, then as 2.0.0."""

    repositories = open_repositories(location)

    for tool in (example_tool(), described_tool("Changed."), versioned_tool("2.0.0")):
        repositories.tools.save_document(tool)


def test_a_tools_versions_are_each_at_its_latest_revision(
    location: str,
    instance: api.Azathoth,
) -> None:
    stock_versions(location)

    versions = instance.tools.versions(TOOL_ID)

    assert [(each.version, each.revision.number) for each in versions] == [
        (TOOL_VERSION, 2),
        ("2.0.0", 1),
    ]
    assert all(each.id == TOOL_ID for each in versions)
    assert versions[0].description == "Changed."
    assert versions[1].command == f"azathoth tool show {TOOL_ID} --version 2.0.0"
    assert all(parses(each.command) for each in versions)


def test_a_tools_versions_are_what_the_list_says_of_it(
    location: str,
    instance: api.Azathoth,
) -> None:
    stock_versions(location)

    assert instance.tools.versions(TOOL_ID) == tuple(
        each for each in instance.tools.list() if each.id == TOOL_ID
    )


def test_an_unknown_tool_has_no_versions_and_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError, match=f"Tool {MISSING_ID} is not configured."):
        instance.tools.versions(MISSING_ID)


def test_tool_versions_prints_each_version_through_the_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stock_versions(str(configure_database(monkeypatch, tmp_path)))

    assert list_tool_versions(TOOL_ID) == 0
    assert capsys.readouterr().out == f"{TOOL_VERSION}\n2.0.0\n"


def test_tool_versions_says_an_unknown_tool_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_database(monkeypatch, tmp_path)

    assert list_tool_versions(MISSING_ID) == 1
    assert capsys.readouterr().err == f"Tool {MISSING_ID} is not configured.\n"

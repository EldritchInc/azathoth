"""Tests that a database from Azathoth 1.0 upgrades as the changelog says.

`tests/fixtures/release-1.0` holds the composition tools exactly as the
v1.0.0 tag shipped them, among its examples: 1.0 had no standard library,
and no `init`, so a 1.0 database holds whichever of them its owner imported.
"""

import json
from pathlib import Path

import pytest

from azathoth.cli import main
from azathoth.tools import (
    decode_tool_document,
    process_tool_environment,
)

PROJECT_ROOT = Path(__file__).parents[1]

RELEASE_1_0 = PROJECT_ROOT / "tests" / "fixtures" / "release-1.0"

CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"

UPGRADED = (
    "Installed tool run_workflow@1.0.0 revision 2.\n"
    "Installed tool loop_workflow@1.1.0 revision 1.\n"
    "Installed tool map_workflow@1.0.0 revision 1.\n"
    "Installed tool json_select@1.0.0 revision 1.\n"
    "Installed tool json_object@1.0.0 revision 1.\n"
    "Installed tool json_merge@1.0.0 revision 1.\n"
    "Installed tool validate_json@1.0.0 revision 1.\n"
    "Installed tool chunk_text@1.0.0 revision 1.\n"
    "Installed tool join_text@1.0.0 revision 1.\n"
    "Installed tool render_template@1.0.0 revision 1.\n"
    "Installed tool split_s3_object@1.0.0 revision 1.\n"
    "Installed tool read_s3_object@1.0.0 revision 1.\n"
)


def release_1_0_documents() -> list[Path]:
    """Return the composition tool documents 1.0 shipped, run first."""

    return [RELEASE_1_0 / "run-workflow.json", RELEASE_1_0 / "loop-workflow.json"]


def test_the_fixtures_are_the_composition_tools_1_0_shipped() -> None:
    shipped = []

    for path in release_1_0_documents():
        document = decode_tool_document(path.read_text(encoding="utf-8"))
        (implementation,) = document.implementations
        shipped.append(
            (document.definition.name, document.definition.version, implementation.environment)
        )

    assert shipped == [("run_workflow", "1.0.0", ()), ("loop_workflow", "1.0.0", ())]


def test_init_upgrades_a_1_0_database_as_the_changelog_shows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    monkeypatch.setenv("AZATHOTH_DATABASE", str(database))

    for path in release_1_0_documents():
        assert main(("tool", "import", str(path))) == 0

    capsys.readouterr()

    assert main(("init",)) == 0

    captured = capsys.readouterr()
    shown = captured.out.replace(str(database), "/path/to/azathoth.db")

    assert captured.err == ""
    assert shown == f"Database: /path/to/azathoth.db (existing)\n{UPGRADED}"
    assert f"```text\n{shown}```" in CHANGELOG.read_text(encoding="utf-8")


def test_the_1_0_loop_gives_its_children_no_database() -> None:
    (implementation,) = decode_tool_document(
        (RELEASE_1_0 / "loop-workflow.json").read_text(encoding="utf-8")
    ).implementations

    environment = process_tool_environment(
        implementation,
        {"PATH": "/usr/bin", "AZATHOTH_DATABASE": "/var/azathoth/azathoth.db"},
        windows=False,
    )

    assert "AZATHOTH_DATABASE" not in environment


def test_the_1_0_run_workflow_is_upgraded_in_place_with_its_grants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AZATHOTH_DATABASE", str(tmp_path / "azathoth.db"))
    run_workflow = decode_tool_document(release_1_0_documents()[0].read_text(encoding="utf-8"))

    assert main(("tool", "import", str(release_1_0_documents()[0]))) == 0
    assert main(("init",)) == 0

    capsys.readouterr()

    assert (
        main(
            (
                "tool",
                "export",
                str(run_workflow.definition.id),
                "--version",
                run_workflow.definition.version,
            )
        )
        == 0
    )

    (implementation,) = json.loads(capsys.readouterr().out)["implementations"]

    assert "AZATHOTH_DATABASE" in implementation["environment"]

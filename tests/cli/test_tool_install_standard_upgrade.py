"""Tests for upgrading a database's standard tools to their environment grants (ADR 0099)."""

import re
from pathlib import Path

import pytest

from azathoth.cli import import_tool, install_standard_tools
from azathoth.revisions import content_digest
from azathoth.standard import standard_tool_documents
from azathoth.tools import (
    POSIX_BASE_ENVIRONMENT,
    WINDOWS_BASE_ENVIRONMENT,
    SQLiteToolRepository,
    ToolDocument,
    encode_tool_document,
)
from tests.cli.test_tool_import import configure_database

PROJECT_ROOT = Path(__file__).parents[2]

CHILD_GRANTS = (
    "AZATHOTH_DATABASE",
    "OPENROUTER_API_KEY",
    "AZATHOTH_WORKFLOW_DEPTH",
    "AZATHOTH_OTEL",
    "OTEL_*",
)

PRE_GRANT_VERSIONS = {"run_workflow": "1.0.0", "loop_workflow": "1.1.0"}

#
# Implementation digests of the standard tools as Azathoth 1.0 shipped them,
# before ADR 0099. The reconstructed documents below must match them exactly.
#
PRE_GRANT_IMPLEMENTATION_DIGESTS = {
    "run_workflow": "7c82bce9a41bbeade40a1cf273da55fe892f045513334c9b89fbf9dac472acf8",
    "loop_workflow": "b49e81e8ba46abe65010fef664faba9c2ff45059e37450081912828d11906678",
}

UPGRADED = (
    "Installed tool run_workflow@1.0.0 revision 2.\n"
    "Installed tool loop_workflow@1.1.0 revision 2.\n"
)


def pre_grant_document(
    document: ToolDocument,
) -> ToolDocument:
    """Return one standard document as it was before its environment grants."""

    return document.model_copy(
        update={
            "implementations": tuple(
                implementation.model_copy(
                    update={
                        "version": PRE_GRANT_VERSIONS[document.definition.name],
                        "environment": (),
                    }
                )
                for implementation in document.implementations
            ),
        }
    )


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Return a database holding the standard tools as they were before ADR 0099."""

    path = tmp_path / "azathoth.db"

    configure_database(database=path, monkeypatch=monkeypatch)

    for document in standard_tool_documents():
        source = tmp_path / f"{document.definition.name}.json"
        source.write_text(encode_tool_document(pre_grant_document(document)), encoding="utf-8")

        assert import_tool(source) == 0

    capsys.readouterr()

    return path


def test_the_reconstructed_documents_are_the_ones_azathoth_1_0_shipped() -> None:
    for document in standard_tool_documents():
        (implementation,) = pre_grant_document(document).implementations

        assert (
            content_digest(implementation)
            == PRE_GRANT_IMPLEMENTATION_DIGESTS[document.definition.name]
        )


def test_installing_over_pre_grant_tools_appends_the_granted_revisions(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert install_standard_tools() == 0

    assert capsys.readouterr().out == UPGRADED

    repository = SQLiteToolRepository(database)

    for document in standard_tool_documents():
        (implementation,) = document.implementations

        current = repository.get_implementation(implementation.id)

        assert current is not None
        assert current.environment == CHILD_GRANTS
        assert current.version == implementation.version


def test_installing_again_after_the_upgrade_writes_nothing(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install_standard_tools()
    capsys.readouterr()

    assert install_standard_tools() == 0
    assert capsys.readouterr().out == (
        "Tool run_workflow@1.0.0 is already installed (revision 2).\n"
        "Tool loop_workflow@1.1.0 is already installed (revision 2).\n"
    )


@pytest.mark.parametrize(
    "path",
    [
        PROJECT_ROOT / "src" / "azathoth" / "standard" / "README.md",
        PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md",
    ],
)
def test_the_documented_upgrade_output_is_the_real_one(
    path: Path,
) -> None:
    assert f"```text\n{UPGRADED}```" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("platform", "variables"),
    [("macOS, Linux", POSIX_BASE_ENVIRONMENT), ("Windows", WINDOWS_BASE_ENVIRONMENT)],
)
def test_the_tools_readme_lists_the_real_base_environment(
    platform: str,
    variables: tuple[str, ...],
) -> None:
    text = (PROJECT_ROOT / "src" / "azathoth" / "tools" / "README.md").read_text(encoding="utf-8")

    (row,) = re.findall(rf"^\| {re.escape(platform)} \| (.*) \|$", text, re.MULTILINE)

    assert tuple(re.findall(r"`([^`]+)`", row)) == variables

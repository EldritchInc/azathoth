"""Tests that the documented standard tool messages and install output are the real ones."""

import json
import re
from pathlib import Path

import pytest
from pydantic import JsonValue

from tests.cli.test_tool_install_standard import ALREADY_INSTALLED, INSTALLED
from tests.standard.harness import run_standard_tool, standard_tool_failure

PROJECT_ROOT = Path(__file__).parents[2]

STANDARD_README = PROJECT_ROOT / "src" / "azathoth" / "standard" / "README.md"

INSTALL_DOCUMENTS = (
    PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md",
    PROJECT_ROOT / "docs" / "install.md",
    PROJECT_ROOT / "docs" / "container.md",
)

TEXT_BLOCK = re.compile(r"```text\n(?P<body>.*?)```", re.DOTALL)

#
# Each failure the standard README documents, with inputs that produce it.
#
DOCUMENTED_FAILURES: tuple[tuple[str, dict[str, JsonValue], int, str], ...] = (
    (
        "json_select",
        {"value": {"story": {}}, "path": ["story", "title"]},
        1,
        'json_select found no value at path ["story", "title"]: missing object key \'title\'.',
    ),
    (
        "json_select",
        {"value": {"chapters": {}}, "path": ["chapters", 0]},
        1,
        'json_select found no value at path ["chapters", 0]: expected a list for index 0.',
    ),
    (
        "json_select",
        {"value": {"chapters": [1, 2]}, "path": ["chapters", 2]},
        1,
        'json_select found no value at path ["chapters", 2]: list index 2 is out of range.',
    ),
    (
        "json_select",
        {"value": {}, "path": "title"},
        2,
        "json_select needs 'path' to be a list of object keys and list indexes.",
    ),
    (
        "json_merge",
        {"base": {}, "patch": []},
        2,
        "json_merge can only merge objects; patch is an array.",
    ),
)


def text_blocks(
    path: Path,
) -> list[str]:
    """Return the body of every `text` block in one document."""

    return [match["body"] for match in TEXT_BLOCK.finditer(path.read_text(encoding="utf-8"))]


@pytest.mark.parametrize(
    ("name", "inputs", "status", "message"),
    [pytest.param(*failure, id=failure[3][:48]) for failure in DOCUMENTED_FAILURES],
)
def test_each_documented_failure_is_the_tools_real_message(
    name: str,
    inputs: dict[str, JsonValue],
    status: int,
    message: str,
) -> None:
    assert standard_tool_failure(name, inputs) == (status, message)
    assert f"{message}\n" in STANDARD_README.read_text(encoding="utf-8")


def test_every_message_the_readme_documents_is_pinned() -> None:
    pinned = {failure[3] for failure in DOCUMENTED_FAILURES}

    documented = {
        line
        for block in text_blocks(STANDARD_README)
        for line in block.splitlines()
        if line.startswith(("json_select ", "json_object ", "json_merge "))
    }

    assert documented == pinned


def test_the_documented_merge_is_the_real_one() -> None:
    (block,) = (block for block in text_blocks(STANDARD_README) if block.startswith("base "))

    rows = dict(line.split(maxsplit=1) for line in block.splitlines())

    output = run_standard_tool(
        "json_merge",
        {"base": json.loads(rows["base"]), "patch": json.loads(rows["patch"])},
    )

    assert output == {"value": json.loads(rows["value"])}


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(path, id=path.relative_to(PROJECT_ROOT).as_posix())
        for path in INSTALL_DOCUMENTS
    ],
)
def test_every_documented_first_install_lists_the_whole_library(
    path: Path,
) -> None:
    blocks = [
        block
        for block in text_blocks(path)
        if "Installed tool run_workflow@1.0.0 revision 1.\n" in block
    ]

    assert blocks

    for block in blocks:
        installed = "".join(
            f"{line}\n" for line in block.splitlines() if line.startswith("Installed tool ")
        )

        assert installed == INSTALLED


def test_the_documented_second_init_reports_the_whole_library_installed() -> None:
    blocks = [
        block
        for block in text_blocks(INSTALL_DOCUMENTS[0])
        if block.startswith("Database: /path/to/azathoth.db (existing)\n")
    ]

    assert blocks == [f"Database: /path/to/azathoth.db (existing)\n{ALREADY_INSTALLED}"]

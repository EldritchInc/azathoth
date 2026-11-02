"""Tests that ADR 0106 states the map tool as the standard library ships it."""

from pathlib import Path

import pytest

from azathoth.standard import standard_tool_documents
from azathoth.tools import ToolDocument

PROJECT_ROOT = Path(__file__).parents[2]

ADR = PROJECT_ROOT / "docs" / "adrs" / "0106-map-a-child-workflow-over-a-list.md"

STANDARD_README = PROJECT_ROOT / "src" / "azathoth" / "standard" / "README.md"


def map_document() -> ToolDocument:
    """Return the standard map tool's document."""

    (document,) = (
        document
        for document in standard_tool_documents()
        if document.definition.name == "map_workflow"
    )

    return document


def settings_table() -> dict[str, str]:
    """Return each setting the ADR's table lists, with its stated default."""

    text = ADR.read_text(encoding="utf-8")
    section = text[text.index("### The tool") : text.index("### Failures")]

    return {
        cells[0].strip("`"): cells[1]
        for line in section.splitlines()
        if line.startswith("| `")
        for cells in [[cell.strip() for cell in line.strip("|").split("|")]]
    }


def test_the_adr_names_the_shipped_tool_and_implementation() -> None:
    document = map_document()
    (implementation,) = document.implementations
    text = ADR.read_text(encoding="utf-8")

    assert f"`map_workflow@{document.definition.version}`" in text
    assert f"tool ID `{document.definition.id}`" in text
    assert f"implementation `{implementation.id}`" in text


def test_the_adr_lists_every_setting_the_tool_accepts() -> None:
    properties = map_document().definition.input_schema.json_schema["properties"]

    assert isinstance(properties, dict)

    accepted = properties["settings"]

    assert isinstance(accepted, dict)
    assert isinstance(accepted["properties"], dict)
    assert list(settings_table()) == list(accepted["properties"])
    assert [
        name for name, default in settings_table().items() if default == "required"
    ] == accepted["required"]


@pytest.mark.parametrize(
    ("setting", "constant"),
    [
        ("max_concurrency", "DEFAULT_MAX_CONCURRENCY"),
        ("child_timeout_seconds", "DEFAULT_CHILD_TIMEOUT_SECONDS"),
        ("budget_seconds", "DEFAULT_BUDGET_SECONDS"),
    ],
)
def test_the_adr_states_the_shipped_defaults(
    setting: str,
    constant: str,
) -> None:
    (implementation,) = map_document().implementations

    assert implementation.source is not None
    assert f"\n{constant} = {settings_table()[setting]}\n" in implementation.source


def test_the_adr_quotes_the_failure_the_standard_readme_documents() -> None:
    (failure,) = (
        line
        for line in STANDARD_README.read_text(encoding="utf-8").splitlines()
        if line.startswith("Item <INDEX> of <COUNT>: child workflow <WORKFLOW_ID> invocation")
    )

    assert f"```text\n{failure}\n```" in ADR.read_text(encoding="utf-8")

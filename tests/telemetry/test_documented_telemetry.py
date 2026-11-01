"""Tests that the tracing documentation names what Azathoth really traces (ADR 0100)."""

import re
from pathlib import Path

from azathoth.standard import standard_tool_documents
from azathoth.telemetry import ATTRIBUTE_KEYS, MISSING_EXTRA_MESSAGE, SPAN_NAMES
from azathoth.telemetry.conventions import ATTEMPT_FAILED_EVENT
from azathoth.tools import MANAGED_ENVIRONMENT_VARIABLES

PROJECT_ROOT = Path(__file__).parents[2]

TELEMETRY_README = PROJECT_ROOT / "src" / "azathoth" / "telemetry" / "README.md"

TOOLS_README = PROJECT_ROOT / "src" / "azathoth" / "tools" / "README.md"

STANDARD_README = PROJECT_ROOT / "src" / "azathoth" / "standard" / "README.md"

TRACING_GUIDES = (
    TELEMETRY_README,
    PROJECT_ROOT / "docs" / "install.md",
    PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md",
)


def section(
    path: Path,
    heading: str,
) -> str:
    """Return the text under one heading, up to the next heading of any level."""

    text = path.read_text(encoding="utf-8")
    start = text.index(f"{heading}\n")
    rest = text[start + len(heading) + 1 :]
    following = re.search(r"^#{1,6} ", rest, re.MULTILINE)

    return rest if following is None else rest[: following.start()]


def first_column(
    text: str,
) -> tuple[str, ...]:
    """Return the code-quoted first cell of every table row."""

    return tuple(re.findall(r"^\| `([^`]+)` \|", text, re.MULTILINE))


def test_the_attribute_table_lists_every_attribute_exactly_once() -> None:
    documented = first_column(section(TELEMETRY_README, "## Attributes"))

    assert len(documented) == len(set(documented))
    assert set(documented) == ATTRIBUTE_KEYS


def test_the_error_table_names_every_span() -> None:
    documented = first_column(section(TELEMETRY_README, "## What Is Traced"))

    assert set(documented) == SPAN_NAMES


def test_the_failed_attempt_event_is_named() -> None:
    assert f"`{ATTEMPT_FAILED_EVENT}`" in TELEMETRY_README.read_text(encoding="utf-8")


def test_the_guides_quote_the_real_missing_extra_message() -> None:
    for path in TRACING_GUIDES:
        assert f"```text\n{MISSING_EXTRA_MESSAGE}\n```" in path.read_text(encoding="utf-8"), path


def test_the_tools_readme_lists_every_managed_variable() -> None:
    documented = first_column(section(TOOLS_README, "## Process Environment"))

    assert tuple(name for name in documented if name in MANAGED_ENVIRONMENT_VARIABLES) == (
        MANAGED_ENVIRONMENT_VARIABLES
    )


def test_the_standard_readme_lists_the_shipped_implementations_and_grants() -> None:
    text = STANDARD_README.read_text(encoding="utf-8")

    for document in standard_tool_documents():
        (implementation,) = document.implementations

        row = (
            rf"^\| `{document.definition.name}` +\| {re.escape(document.definition.version)} +"
            rf"\| {re.escape(implementation.version)} +\|"
        )

        assert re.search(row, text, re.MULTILINE), document.definition.name

        for grant in implementation.environment:
            assert f'"{grant}"' in text, grant

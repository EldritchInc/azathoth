"""Tests that the persistence documentation names what Azathoth really does (ADR 0102)."""

import re
from pathlib import Path

import pytest

from azathoth.persistence import (
    MISSING_DRIVER_MESSAGE,
    SCHEMA_TABLE,
    DatabaseNotInitializedError,
    DatabaseSchemaOutdatedError,
    DatabaseSchemaTooNewError,
    PostgresLocation,
    redact_url,
)
from azathoth.persistence.dialect import TOKENS, Dialect
from azathoth.persistence.repositories import SCHEMA_TABLES

PROJECT_ROOT = Path(__file__).parents[2]

PERSISTENCE_README = PROJECT_ROOT / "src" / "azathoth" / "persistence" / "README.md"

CLI_README = PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md"

POSTGRES_GUIDES = (
    PERSISTENCE_README,
    CLI_README,
    PROJECT_ROOT / "docs" / "install.md",
    PROJECT_ROOT / "docs" / "container.md",
)

POSTGRES_URL = re.compile(r"postgres(?:ql)?://[^\s\"'`)]+")


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


def rows(
    text: str,
) -> tuple[tuple[str, ...], ...]:
    """Return the cells of every table row whose first cell is code-quoted."""

    return tuple(
        tuple(cell.strip().strip("`") for cell in line.strip("|").split("|"))
        for line in text.splitlines()
        if line.startswith("| `")
    )


def test_the_table_list_names_every_table_in_creation_order() -> None:
    documented = tuple(row[0] for row in rows(section(PERSISTENCE_README, "## Tables")))

    assert documented == tuple(table.name for table in SCHEMA_TABLES)


def test_the_schema_version_table_is_named() -> None:
    assert f"`{SCHEMA_TABLE}`" in PERSISTENCE_README.read_text(encoding="utf-8")


def test_the_token_table_spells_every_token_as_the_dialects_do() -> None:
    documented = rows(section(PERSISTENCE_README, "# Writing SQL Once"))

    assert documented == tuple(
        (token, spellings[Dialect.SQLITE], spellings[Dialect.POSTGRES])
        for token, spellings in TOKENS.items()
    )


@pytest.mark.parametrize("guide", (PERSISTENCE_README, CLI_README))
def test_the_missing_driver_message_is_quoted_exactly(
    guide: Path,
) -> None:
    assert f"\n{MISSING_DRIVER_MESSAGE}\n" in guide.read_text(encoding="utf-8")


def test_the_schema_refusals_are_quoted_exactly() -> None:
    location = PostgresLocation("postgresql://db.example.com/azathoth")
    documented = section(PERSISTENCE_README, "# The Schema")

    for found, error in (
        (None, DatabaseNotInitializedError(location)),
        (0, DatabaseSchemaOutdatedError(location, found=0, expected=1)),
        (2, DatabaseSchemaTooNewError(location, found=2, expected=1)),
    ):
        lines = [
            line.replace("<URL>", location.display())
            .replace("<FOUND>", str(found))
            .replace("<EXPECTED>", "1")
            for line in documented.splitlines()
        ]

        assert str(error) in lines


@pytest.mark.parametrize("guide", POSTGRES_GUIDES)
def test_a_password_is_never_shown_in_output(
    guide: Path,
) -> None:
    text = guide.read_text(encoding="utf-8")
    outputs = re.findall(r"```text\n(.*?)```", text, re.DOTALL)
    shown = [url for output in outputs for url in POSTGRES_URL.findall(output)]

    assert all(redact_url(url) == url for url in shown)


@pytest.mark.parametrize("guide", POSTGRES_GUIDES)
def test_every_shown_database_is_the_redacted_url_the_guide_sets(
    guide: Path,
) -> None:
    text = guide.read_text(encoding="utf-8")
    outputs = re.findall(r"```text\n(.*?)```", text, re.DOTALL)
    shown = {url for output in outputs for url in POSTGRES_URL.findall(output)}
    configured = {redact_url(url) for url in POSTGRES_URL.findall(text) if "<PASSWORD>" in url}

    assert shown <= configured

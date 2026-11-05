"""Tests that the changelog records this release, its decisions and its upgrade."""

import re
from pathlib import Path

import pytest

from azathoth import __version__

PROJECT_ROOT = Path(__file__).parents[1]

CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"

ADRS = PROJECT_ROOT / "docs" / "adrs"

REPOSITORY = "https://github.com/EldritchInc/azathoth/blob/main"
"""Where the changelog links, so its links work in a GitHub release's notes too."""

RELEASE_HEADING = re.compile(r"^## (\d+\.\d+\.\d+)$", re.MULTILINE)

ENTRY_HEADING = re.compile(r"^## (\S.*)$", re.MULTILINE)

UNRELEASED = "Unreleased"
"""The entry for what is on `main` but not yet released, renamed when it is."""

FIRST_ADR_OF_1_1 = 91

FIRST_ADR_AFTER_1_1 = 111

#
# The command RELEASING.md gives for a release's notes, with its version.
#
NOTES_COMMAND = (
    'awk -v version=<version> \'$0 == "## " version {found = 1; next} '
    "/^## / {found = 0} found' CHANGELOG.md > release-notes.md"
)


def text() -> str:
    """Return the changelog."""

    return CHANGELOG.read_text(encoding="utf-8")


def entry(
    version: str,
) -> str:
    """Return one release's entry, as RELEASING.md's command extracts it."""

    lines = []
    found = False

    for line in text().splitlines():
        if line == f"## {version}":
            found = True
            continue

        if line.startswith("## "):
            found = False

        if found:
            lines.append(line)

    return "\n".join(lines)


def fenced(
    document: str,
    language: str,
    after: str,
) -> str:
    """Return the first block of a language after a heading in one document."""

    start = document.index(after)
    opening = document.index(f"```{language}\n", start) + len(f"```{language}\n")

    return document[opening : document.index("```", opening)]


def test_the_releases_are_listed_newest_first_starting_with_this_one() -> None:
    releases = RELEASE_HEADING.findall(text())

    assert releases == ["1.1.0", "1.0.0"]
    assert releases[0] == __version__


def decision_numbers() -> set[int]:
    """Return the number of every decision record."""

    return {int(path.name[:4]) for path in ADRS.glob("[0-9][0-9][0-9][0-9]-*.md")}


def cited_numbers(
    version: str,
) -> set[int]:
    """Return the number of every decision one entry cites."""

    return {int(number) for number in re.findall(r"ADR (\d{4})", entry(version))}


def test_the_unreleased_entry_comes_before_every_release() -> None:
    assert ENTRY_HEADING.findall(text()) == [UNRELEASED, "1.1.0", "1.0.0"]


def test_this_releases_entry_cites_every_decision_made_for_it() -> None:
    decided = decision_numbers() & set(range(FIRST_ADR_OF_1_1, FIRST_ADR_AFTER_1_1))

    assert cited_numbers(__version__) == decided


def test_the_unreleased_entry_cites_every_decision_made_since() -> None:
    decided = {number for number in decision_numbers() if number >= FIRST_ADR_AFTER_1_1}

    assert decided
    assert cited_numbers(UNRELEASED) == decided


@pytest.mark.parametrize("version", [__version__, UNRELEASED])
def test_every_cited_decision_links_its_record(
    version: str,
) -> None:
    for number in re.findall(r"ADR (\d{4})", entry(version)):
        (path,) = ADRS.glob(f"{number}-*.md")

        assert f"]({REPOSITORY}/docs/adrs/{path.name})" in text(), number


def test_the_upgrade_runs_the_install_guides_upgrade_commands() -> None:
    install = (PROJECT_ROOT / "docs" / "install.md").read_text(encoding="utf-8")
    upgrade = entry(__version__)

    for language in ("bash", "powershell"):
        assert fenced(upgrade, language, "### Upgrading From 1.0") == fenced(
            install, language, "## Upgrading, Leaving and Uninstalling"
        )


def test_the_upgrade_names_the_one_breaking_change() -> None:
    upgrade = entry(__version__)

    assert "Process tools no longer inherit Azathoth's environment" in upgrade
    assert f"]({REPOSITORY}/src/azathoth/tools/README.md#process-environment)" in upgrade


def test_releasing_publishes_this_entry_as_the_github_release() -> None:
    releasing = (PROJECT_ROOT / "RELEASING.md").read_text(encoding="utf-8")

    assert NOTES_COMMAND in releasing
    assert (
        'gh release create v<version> --title "Azathoth <version>" '
        "--notes-file release-notes.md" in releasing
    )
    assert entry(__version__).strip()


def test_every_link_is_absolute_so_it_works_in_the_release_notes() -> None:
    targets = re.findall(r"\]\(([^)]+)\)", text())

    assert targets
    assert all(target.startswith("https://") for target in targets), targets

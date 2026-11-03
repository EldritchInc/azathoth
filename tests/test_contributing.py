"""Tests that CONTRIBUTING says where to ask, where to start, and where to hire help."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]

CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"

RELEASE_VALIDATION = PROJECT_ROOT / "docs" / "release-validation.md"

DISCUSSIONS = "https://github.com/EldritchInc/azathoth/discussions"

GOOD_FIRST_ISSUES = (
    "https://github.com/EldritchInc/azathoth/issues"
    "?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22"
)

WORK_WITH_US = "https://eldritchinc.com/workwithus/"


def getting_involved() -> str:
    """Return CONTRIBUTING's Getting Involved section."""

    text = CONTRIBUTING.read_text(encoding="utf-8")
    start = text.index("\n## Getting Involved\n")

    return text[start : text.index("\n## ", start + 1)]


def test_getting_involved_comes_before_the_development_guide() -> None:
    text = CONTRIBUTING.read_text(encoding="utf-8")

    assert text.index("\n## Getting Involved\n") < text.index("\n## Development Environment\n")


def test_it_links_discussions_good_first_issues_and_commercial_help() -> None:
    section = getting_involved()

    for link in (DISCUSSIONS, GOOD_FIRST_ISSUES, WORK_WITH_US):
        assert f"]({link})" in section, link


def test_a_release_requires_discussions_and_good_first_issues_to_exist() -> None:
    checklist = RELEASE_VALIDATION.read_text(encoding="utf-8")

    assert "[ ] Discussions are enabled, and open good first issues are labeled\n" in checklist

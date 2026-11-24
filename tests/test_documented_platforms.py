"""Tests that ADR 0142 and the guides say where serving and the worker are tested, exactly.

They quote what serving a remote and running the queue worker say on
Windows, and why a run skips their tests there, as the code says them.
"""

from pathlib import Path

from azathoth.cli.platforms import SERVING_ON_WINDOWS_WARNING, WORKER_ON_WINDOWS_WARNING
from tests.conftest import SERVER_REASON

ROOT = Path(__file__).parents[1]

ADRS = ROOT / "docs" / "adrs"

ADR = ADRS / "0142-remotes-are-served-from-linux-and-macos.md"

LINK = (
    "https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/"
    "0142-remotes-are-served-from-linux-and-macos.md"
)


def text(
    document: Path,
) -> str:
    return document.read_text(encoding="utf-8")


def flat(
    document: Path,
) -> str:
    """Return a document with its lines joined, as prose reads across them."""

    return " ".join(text(document).split())


def quoted(
    document: Path,
    message: str,
) -> bool:
    """Return whether a document quotes one message as a line of its own."""

    return f"\n{message}\n" in text(document)


def test_the_decision_quotes_both_warnings_and_why_a_run_skips() -> None:
    assert quoted(ADR, SERVING_ON_WINDOWS_WARNING)
    assert quoted(ADR, WORKER_ON_WINDOWS_WARNING)
    assert quoted(ADR, SERVER_REASON)
    assert "`server`" in flat(ADR)
    assert "`tests/conftest.py`" in flat(ADR)


def test_the_decision_is_listed() -> None:
    assert text(ADR).startswith(
        "# ADR 0142: Remotes Are Served from Linux and macOS\n\n"
        "- Status: Accepted\n- Date: 2026-11-24\n"
    )
    assert (
        "- [ADR 0142: Remotes Are Served from Linux and macOS]"
        "(0142-remotes-are-served-from-linux-and-macos.md)"
    ) in text(ADRS / "README.md")


def test_the_remote_guide_quotes_what_serving_on_windows_says() -> None:
    assert quoted(ROOT / "docs" / "remote.md", SERVING_ON_WINDOWS_WARNING)
    assert "WSL 2" in flat(ROOT / "docs" / "remote.md")


def test_the_install_guide_quotes_what_the_worker_says_on_windows() -> None:
    assert quoted(ROOT / "docs" / "install.md", WORKER_ON_WINDOWS_WARNING)


def test_the_readme_says_where_serving_and_the_worker_are_tested() -> None:
    assert (
        "Serving a remote and running the queue worker are tested on Linux and macOS; on "
        "Windows they run at your own risk"
    ) in flat(ROOT / "README.md")


def test_release_validation_says_what_windows_skips() -> None:
    assert (
        "On Windows it skips the tests of serving a remote and running the queue worker, "
        "saying why (ADR 0142)."
    ) in flat(ROOT / "docs" / "release-validation.md")


def test_the_changelog_cites_the_decision() -> None:
    entry = text(ROOT / "CHANGELOG.md").split("\n## ", 2)[1]

    assert f"({LINK})" in entry
    assert "### Serving on Windows" in entry

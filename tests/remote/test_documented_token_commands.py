"""Tests that ADR 0141, the READMEs, the guide and the changelog say what a token command does.

Each refusal a document quotes is made by running a command that fails as
it says, with the command and what it said put back as placeholders, so a
document quotes exactly what a refusal says. How long a command may run,
how long its token is kept and how much of what it said is shown are read
from the code.
"""

import sys
from pathlib import Path

import pytest

from azathoth.cli.remote import named_line
from azathoth.remote import (
    BOTH_TOKEN_SOURCES_MESSAGE,
    OPAQUE_TOKEN_SECONDS,
    TOKEN_COMMAND_TIMEOUT_SECONDS,
    TOKEN_REFRESH_MARGIN_SECONDS,
    NamedRemote,
    TokenCommandError,
    printed_token,
    shown_command,
)
from azathoth.remote.token_commands import MAX_ERROR_SHOWN
from tests.persistence.test_remote_repository import START

ROOT = Path(__file__).parents[2]

ADRS = ROOT / "docs" / "adrs"

ADR = ADRS / "0141-tokens-printed-by-a-command.md"

AMENDED = ADRS / "0126-named-remotes.md"

CLI = ROOT / "src" / "azathoth" / "cli" / "README.md"

API = ROOT / "src" / "azathoth" / "api" / "README.md"

GUIDE = ROOT / "docs" / "remote.md"

CHANGELOG = ROOT / "CHANGELOG.md"

LINK = "https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/0141-tokens-printed-by-a-command.md"

GCLOUD = ("gcloud", "auth", "print-identity-token")

TEAM = "https://azathoth.example.com"

BY_COMMAND = NamedRemote(
    name="team",
    url=TEAM,
    token_variable=None,
    token_command=GCLOUD,
    added_at=START,
)
"""A remote named with the command its token is printed by."""


def text(
    document: Path,
) -> str:
    return document.read_text(encoding="utf-8")


def flat(
    document: Path,
) -> str:
    """Return a document with its lines joined, as prose reads across them."""

    return " ".join(text(document).split())


def documented(
    document: Path,
    message: str,
) -> None:
    """Require a document to quote one message, as a line of its own."""

    assert f"\n{message}\n" in text(document), (document.name, message)


def refusal(
    command: tuple[str, ...],
    *,
    timeout: float = TOKEN_COMMAND_TIMEOUT_SECONDS,
) -> str:
    """Return what running a command that fails says, its command put back as `<COMMAND>`."""

    with pytest.raises(TokenCommandError) as caught:
        printed_token(command, timeout=timeout)

    return str(caught.value).replace(shown_command(command), "<COMMAND>")


def python(
    source: str,
) -> tuple[str, ...]:
    return (sys.executable, "-c", source)


def refusals() -> list[str]:
    """Return every refusal of a command's run, as the documents quote them."""

    failed = refusal(python("import sys; sys.stderr.write('<SAID>'); sys.exit(1)")).replace(
        "status 1:", "status <STATUS>:"
    )
    slow = refusal(python("import time; time.sleep(10)"), timeout=0.5).replace(
        "within 0.5 seconds", f"within {TOKEN_COMMAND_TIMEOUT_SECONDS:g} seconds"
    )
    missing = refusal(("azathoth-no-such-program", "token")).replace(
        "azathoth-no-such-program", "<PROGRAM>"
    )

    return [
        failed,
        refusal(python("print()")),
        refusal(python("print('one two')")),
        slow,
        missing,
    ]


def test_the_refusals_are_made_as_the_documents_quote_them() -> None:
    assert refusals() == [
        "Token command `<COMMAND>` exited with status <STATUS>: <SAID>",
        "Token command `<COMMAND>` printed no token.",
        "Token command `<COMMAND>` printed more than a token: it must print the token alone, "
        "on one line.",
        "Token command `<COMMAND>` printed no token within 30 seconds.",
        "Token command `<COMMAND>` could not be run: <PROGRAM> was not found.",
    ]


def test_the_decision_quotes_what_naming_and_running_a_command_say() -> None:
    documented(ADR, BOTH_TOKEN_SOURCES_MESSAGE)
    documented(ADR, named_line(BY_COMMAND))

    for message in refusals():
        documented(ADR, message)


def test_the_decision_says_how_long_a_command_runs_and_its_token_is_kept() -> None:
    decision = flat(ADR)

    assert f"{TOKEN_COMMAND_TIMEOUT_SECONDS:g} seconds to print" in decision
    assert f"until {TOKEN_REFRESH_MARGIN_SECONDS:g} seconds before" in decision
    assert f"for {OPAQUE_TOKEN_SECONDS / 60:g} minutes" in decision
    assert f"its last {MAX_ERROR_SHOWN} characters" in decision
    assert "`remote_token_commands`" in decision
    assert "schema version 9" in decision
    assert "`api.token_of`" in decision


def test_the_decision_amends_the_one_it_says_and_is_listed() -> None:
    status = next(line for line in text(AMENDED).splitlines() if line.startswith("- Status:"))

    assert status == "- Status: Accepted; amended by ADR 0141"
    assert text(ADR).startswith(
        "# ADR 0141: Tokens Printed by a Command\n\n- Status: Accepted\n- Date: 2026-11-24\n"
    )
    assert "- [ADR 0141: Tokens Printed by a Command](0141-tokens-printed-by-a-command.md)" in text(
        ADRS / "README.md"
    )


def test_the_command_line_guide_quotes_naming_a_remote_by_its_command() -> None:
    named = BY_COMMAND

    documented(CLI, BOTH_TOKEN_SOURCES_MESSAGE)
    documented(CLI, named_line(named))
    documented(
        CLI, f"Named remote team for {TEAM}; its token is printed by `{shown_command(GCLOUD)}`."
    )
    assert "--token-command" in text(CLI)


def test_the_api_guide_names_token_of_and_the_command() -> None:
    guide = flat(API)

    assert "`api.token_of(remote, environ=None)`" in guide
    assert "token_command=[" in text(API)
    assert "`token_command`" in guide
    documented(API, BOTH_TOKEN_SOURCES_MESSAGE)


def test_the_remote_guide_names_a_remote_by_its_command_and_troubleshoots_one() -> None:
    assert "--token-command" in text(GUIDE)
    documented(GUIDE, refusals()[0])


def test_the_changelog_cites_the_decision_and_the_schema_it_moves_to() -> None:
    entry = text(CHANGELOG).split("\n## ", 2)[1]

    assert f"({LINK})" in entry
    assert "--token-command" in entry
    assert "The database schema moves from version 7 to version 9" in entry

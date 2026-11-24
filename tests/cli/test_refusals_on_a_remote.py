"""Tests that every command given `--remote` refuses alike when it cannot be used (ADR 0140).

A remote with no such name, one whose token is not set, one that cannot be
reached, and one whose policy refuses the caller are each reported in one
line on standard error, with status 1 and nothing on standard output, by
every command that runs on a remote. Each command is given the least its
parser accepts, so none of them is left out.
"""

import argparse
import re
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID

import httpx
import pytest

from azathoth import api
from azathoth.cli import main
from azathoth.cli.parsing import build_parser
from azathoth.cli.parsing.targets import NEVER_ON_A_REMOTE, REMOTE_ATTRIBUTE, command_parsers
from azathoth.remote import Principal
from tests.cli.test_remote_option import Reaching
from tests.cli.test_workflow_run import configure_database
from tests.remote.test_call_routes import Served

URL = "http://remote.test"

TOKEN_VARIABLE = "AZATHOTH_ORIGIN_TOKEN"

UNKNOWN_ID = "c1400000-0000-4000-8000-0000000000ff"

GIVEN_FILE = "given.json"
"""The file each command that reads one is given: a job request for an unknown workflow."""

GIVEN_REQUEST = (
    '{"kind": "invoke", "version": 1, "idempotency_key": "refused", '
    f'"workflow_id": "{UNKNOWN_ID}", "input": {{"value": "x"}}}}'
)

GIVEN: dict[str, tuple[str, ...]] = {
    "tool from-mcp": ("--url", "https://mcp.example.com/mcp"),
}
"""What a command is given beyond its parser's least, where its handler needs more."""

MALLORY = Principal(name="Mallory", owner=False)
"""A caller the core's policy refuses everything."""

REFUSED = re.compile(r"Mallory may not [A-Za-z ]+ on this remote: only its owner may\.\n")
"""How the core's policy refuses Mallory, in one line."""


def _value(
    action: argparse.Action,
) -> str:
    """Return a value a parser takes for one argument: its first choice, or one of its type."""

    if action.choices:
        return str(next(iter(action.choices)))

    kind = getattr(action.type, "__name__", "")

    if action.type is UUID:
        return UNKNOWN_ID

    if "json" in kind:
        return '"x"'

    if action.type in (int, float) or "integer" in kind or "positive" in kind:
        return "1"

    if action.type is Path or action.dest.endswith(("document", "request")):
        return GIVEN_FILE

    return "x"


def _given(
    action: argparse.Action,
) -> list[str]:
    """Return an option and the value it is given, or the option alone for a flag."""

    return (
        [action.option_strings[0]]
        if action.nargs == 0
        else [action.option_strings[0], _value(action)]
    )


def least_arguments(
    command: str,
    parser: argparse.ArgumentParser,
) -> tuple[str, ...]:
    """Return a command with the least its parser accepts: every argument it requires."""

    words = command.split()

    for action in parser._actions:
        if isinstance(action, argparse._HelpAction) or action.dest == REMOTE_ATTRIBUTE:
            continue

        if not action.option_strings:
            if action.nargs not in ("*", "?"):
                words.extend(
                    [_value(action)] * (action.nargs if isinstance(action.nargs, int) else 1)
                )
        elif action.required:
            words.extend(_given(action))

    for group in parser._mutually_exclusive_groups:
        if group.required:
            words.extend(_given(group._group_actions[0]))

    return (*words, *GIVEN.get(command, ()))


COMMANDS = [
    least_arguments(command, parser)
    for command, parser in command_parsers(build_parser())
    if command not in NEVER_ON_A_REMOTE
]
"""Every command that runs on a remote, with the least its parser accepts."""


def test_every_command_is_given_what_its_parser_accepts() -> None:
    assert len(COMMANDS) == 72

    for command in COMMANDS:
        build_parser().parse_args(command)


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the command line at a database naming the remote `origin`, with its token set."""

    configured = configure_database(monkeypatch, tmp_path)
    configured.touch()
    monkeypatch.chdir(tmp_path)
    (tmp_path / GIVEN_FILE).write_text(GIVEN_REQUEST, encoding="utf-8")

    with api.open(configured) as instance:
        instance.remotes.add("origin", URL, token_variable=TOKEN_VARIABLE)

    monkeypatch.setenv(TOKEN_VARIABLE, "azr_origin")

    return configured


def said(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    status = main(arguments)
    printed = capsys.readouterr()

    return status, printed.out, printed.err


def refusal(
    database: Path,
    target: str,
) -> str:
    """Return what finding or connecting to the remote `target` names is refused with."""

    with api.open(database) as instance, pytest.raises(api.ApiError) as raised:
        instance.remote(target).connect()

    return str(raised.value)


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_a_remote_with_no_such_name_is_refused_alike_by_every_command(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    command: tuple[str, ...],
) -> None:
    message = refusal(database, "nowhere")

    assert said(capsys, *command, "--remote", "nowhere") == (1, "", f"{message}\n")


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_a_remote_whose_token_is_not_set_is_refused_alike_by_every_command(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: tuple[str, ...],
) -> None:
    monkeypatch.delenv(TOKEN_VARIABLE)
    message = refusal(database, "origin")

    assert said(capsys, *command, "--remote", "origin") == (1, "", f"{message}\n")


class Unreachable:
    """An HTTP client whose every request fails as one to a remote that is down does."""

    def __init__(
        self,
        **_: Any,
    ) -> None:
        pass

    def request(
        self,
        *_: Any,
        **__: Any,
    ) -> NoReturn:
        raise httpx.ConnectError("Connection refused")

    def stream(
        self,
        *_: Any,
        **__: Any,
    ) -> NoReturn:
        raise httpx.ConnectError("Connection refused")

    def close(
        self,
    ) -> None:
        pass


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_a_remote_that_cannot_be_reached_is_reported_in_one_line_by_every_command(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: tuple[str, ...],
) -> None:
    monkeypatch.setattr(httpx, "Client", Unreachable)

    status, printed, err = said(capsys, *command, "--remote", "origin")

    assert (status, printed) == (1, ""), command
    assert err == f"The remote at {URL} could not be reached: Connection refused\n", command


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_a_caller_the_remote_refuses_is_told_why_in_one_line_by_every_command(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: tuple[str, ...],
) -> None:
    monkeypatch.setattr(httpx, "Client", Reaching(Served(database, principal=MALLORY)))

    status, printed, err = said(capsys, *command, "--remote", "origin")

    assert (status, printed) == (1, ""), command
    assert REFUSED.fullmatch(err), (command, err)

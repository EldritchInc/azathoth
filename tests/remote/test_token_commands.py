"""Tests for the commands a named remote's token is printed by (ADR 0141).

A command is run as its arguments, never through a shell, given no input,
and has a while to print the token alone on standard output; what it says
on standard error is shown when it fails. Its token is kept in the process
until shortly before the expiry a JWT names, or for a few minutes otherwise.
"""

import base64
import json
import sys
from pathlib import Path

import pytest

from azathoth.remote import (
    OPAQUE_TOKEN_SECONDS,
    TOKEN_COMMAND_TIMEOUT_SECONDS,
    TOKEN_REFRESH_MARGIN_SECONDS,
    TokenCache,
    TokenCommandError,
    expires_at,
    printed_token,
    require_token_command,
    shown_command,
)

PYTHON = sys.executable


def python(
    source: str,
) -> tuple[str, ...]:
    """Return the command that runs a line of Python, as a token command does."""

    return (PYTHON, "-c", source)


def printing_in_turn(
    count: Path,
    *tokens: str,
) -> tuple[str, ...]:
    """Return a command that prints each token in turn, counting its runs in the file `count`."""

    source = (
        "import pathlib, sys; count = pathlib.Path(sys.argv[1]); "
        "ran = int(count.read_text()) if count.exists() else 0; "
        "count.write_text(str(ran + 1)); print(sys.argv[2 + ran])"
    )

    return (*python(source), str(count), *tokens)


def runs(
    count: Path,
) -> int:
    """Return how many times a command `printing_in_turn` made was run."""

    return int(count.read_text()) if count.exists() else 0


def jwt(
    claims: object,
) -> str:
    """Return a JWT holding `claims`, its header and signature made up, as none is checked."""

    def part(value: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    return f"{part({'alg': 'RS256', 'typ': 'JWT'})}.{part(claims)}.c2lnbmF0dXJl"


# What a command is


def test_a_command_is_its_arguments() -> None:
    assert require_token_command(["gcloud", "auth", "print-identity-token"]) == (
        "gcloud",
        "auth",
        "print-identity-token",
    )


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ((), "A token command names the program that prints the token; it was empty."),
        (("",), "A token command names the program that prints the token; it was empty."),
        (
            ("printf", "a\0b"),
            "A token command's arguments may not hold a NUL character.",
        ),
    ],
    ids=["empty", "no-program", "nul"],
)
def test_a_command_that_is_not_one_is_refused(
    command: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(TokenCommandError) as caught:
        require_token_command(command)

    assert str(caught.value) == message


def test_a_command_given_as_one_string_is_refused_since_no_shell_splits_it() -> None:
    with pytest.raises(TokenCommandError) as caught:
        require_token_command("gcloud auth print-identity-token")

    assert str(caught.value) == (
        "A token command is given as its arguments, not as one string: split it as a shell "
        "would, as shlex.split does."
    )


def test_a_command_is_shown_as_a_shell_would_read_it() -> None:
    assert shown_command(("az", "account", "get-access-token", "--query", "accessToken")) == (
        "az account get-access-token --query accessToken"
    )
    assert shown_command(("printf", "two words")) == "printf 'two words'"


# Running a command


def test_a_command_prints_its_token_alone() -> None:
    assert printed_token(python("print('  azr_printed  ')")) == "azr_printed"


def test_a_command_printing_in_turn_counts_its_runs(
    tmp_path: Path,
) -> None:
    command = printing_in_turn(tmp_path / "count", "azr_first", "azr_second")

    assert [printed_token(command), printed_token(command)] == ["azr_first", "azr_second"]
    assert runs(tmp_path / "count") == 2


def test_a_command_is_run_without_a_shell(
    tmp_path: Path,
) -> None:
    witness = tmp_path / "ran"
    command = python(f"import sys; print(sys.argv[1])  # $(touch {witness})") + ("$HOME;x",)

    assert printed_token(command) == "$HOME;x"
    assert not witness.exists()


def test_a_command_is_given_no_input() -> None:
    assert printed_token(python("import sys; print(repr(sys.stdin.read()) + 'x')")) == "''x"


def test_a_command_that_fails_says_what_it_said_on_standard_error() -> None:
    command = python("import sys; sys.stderr.write('You are not signed in.\\n'); sys.exit(3)")

    with pytest.raises(TokenCommandError) as caught:
        printed_token(command)

    assert str(caught.value) == (
        f"Token command `{shown_command(command)}` exited with status 3: You are not signed in."
    )


def test_a_command_that_fails_saying_nothing_says_so() -> None:
    command = python("raise SystemExit(1)")

    with pytest.raises(TokenCommandError) as caught:
        printed_token(command)

    assert str(caught.value) == (
        f"Token command `{shown_command(command)}` exited with status 1, saying nothing on "
        "standard error."
    )


def test_what_a_failing_command_said_is_shown_on_one_line_and_its_end_kept() -> None:
    command = python("import sys; sys.stderr.write('a\\n' * 10 + 'b' * 600); sys.exit(1)")

    with pytest.raises(TokenCommandError) as caught:
        printed_token(command)

    said = str(caught.value).split(": ", 1)[1]

    assert said == "…" + "b" * 500
    assert "\n" not in str(caught.value)


def test_a_command_not_found_says_so() -> None:
    command = ("azathoth-no-such-program", "token")

    with pytest.raises(TokenCommandError) as caught:
        printed_token(command)

    assert str(caught.value) == (
        "Token command `azathoth-no-such-program token` could not be run: "
        "azathoth-no-such-program was not found."
    )


def test_a_command_that_takes_too_long_is_stopped() -> None:
    command = python("import time; time.sleep(10)")

    with pytest.raises(TokenCommandError) as caught:
        printed_token(command, timeout=0.5)

    assert str(caught.value) == (
        f"Token command `{shown_command(command)}` printed no token within 0.5 seconds."
    )
    assert TOKEN_COMMAND_TIMEOUT_SECONDS == 30.0


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("print('   ')", "printed no token."),
        (
            "print('azr_one'); print('azr_two')",
            "printed more than a token: it must print the token alone, on one line.",
        ),
        (
            "print('Bearer azr_one')",
            "printed more than a token: it must print the token alone, on one line.",
        ),
    ],
    ids=["nothing", "two-lines", "two-words"],
)
def test_a_command_must_print_one_token(
    source: str,
    message: str,
) -> None:
    command = python(source)

    with pytest.raises(TokenCommandError) as caught:
        printed_token(command)

    assert str(caught.value) == f"Token command `{shown_command(command)}` {message}"


# When a token expires


def test_a_jwt_says_when_it_expires() -> None:
    assert expires_at(jwt({"sub": "eris", "exp": 1_800_000_000})) == 1_800_000_000.0
    assert expires_at(jwt({"exp": 1_800_000_000.5})) == 1_800_000_000.5


@pytest.mark.parametrize(
    "token",
    [
        "azr_opaque",
        "one.two",
        "not.base64!.at-all",
        f"{jwt({})}",
        f"{jwt({'exp': 'tomorrow'})}",
        f"{jwt({'exp': True})}",
        f"{jwt(['exp', 1])}",
        "e30.bm90IGpzb24.c2ln",
    ],
    ids=["opaque", "two-parts", "not-base64", "no-exp", "text", "bool", "list", "not-json"],
)
def test_a_token_naming_no_expiry_has_none(
    token: str,
) -> None:
    assert expires_at(token) is None


# Keeping a token


class Printing:
    """A token command's stand-in that prints the tokens given, one each run."""

    def __init__(
        self,
        *tokens: str,
    ) -> None:
        self.tokens = list(tokens)
        self.runs: list[tuple[str, ...]] = []

    def __call__(
        self,
        command: tuple[str, ...],
    ) -> str:
        self.runs.append(command)

        return self.tokens.pop(0)


class Clock:
    """A clock that says the time it is set to."""

    def __init__(
        self,
        now: float,
    ) -> None:
        self.now = now

    def __call__(
        self,
    ) -> float:
        return self.now


COMMAND = ("gcloud", "auth", "print-identity-token")

NOW = 1_800_000_000.0


def test_an_opaque_token_is_kept_for_a_few_minutes() -> None:
    printing = Printing("azr_first", "azr_second")
    clock = Clock(NOW)
    cache = TokenCache(run=printing, clock=clock)

    assert cache.token(COMMAND) == "azr_first"

    clock.now = NOW + OPAQUE_TOKEN_SECONDS - 1

    assert cache.token(COMMAND) == "azr_first"

    clock.now = NOW + OPAQUE_TOKEN_SECONDS

    assert cache.token(COMMAND) == "azr_second"
    assert printing.runs == [COMMAND, COMMAND]
    assert OPAQUE_TOKEN_SECONDS == 300.0


def test_a_jwt_is_kept_until_shortly_before_it_expires() -> None:
    first = jwt({"exp": NOW + 3600})
    second = jwt({"exp": NOW + 7200})
    printing = Printing(first, second)
    clock = Clock(NOW)
    cache = TokenCache(run=printing, clock=clock)

    assert cache.token(COMMAND) == first

    clock.now = NOW + 3600 - TOKEN_REFRESH_MARGIN_SECONDS - 1

    assert cache.token(COMMAND) == first

    clock.now = NOW + 3600 - TOKEN_REFRESH_MARGIN_SECONDS

    assert cache.token(COMMAND) == second
    assert len(printing.runs) == 2
    assert TOKEN_REFRESH_MARGIN_SECONDS == 30.0


def test_a_jwt_about_to_expire_is_used_once_and_not_kept() -> None:
    expiring = jwt({"exp": NOW + 10})
    printing = Printing(expiring, "azr_fresh")
    cache = TokenCache(run=printing, clock=Clock(NOW))

    assert cache.token(COMMAND) == expiring
    assert cache.token(COMMAND) == "azr_fresh"


def test_each_command_keeps_its_own_token() -> None:
    other = ("az", "account", "get-access-token")
    printing = Printing("azr_google", "azr_azure")
    cache = TokenCache(run=printing, clock=Clock(NOW))

    assert cache.token(COMMAND) == "azr_google"
    assert cache.token(list(other)) == "azr_azure"
    assert cache.token(COMMAND) == "azr_google"
    assert printing.runs == [COMMAND, other]


def test_a_command_that_fails_keeps_nothing_and_is_run_again() -> None:
    failures = 0

    def failing_once(command: tuple[str, ...]) -> str:
        nonlocal failures

        if failures == 0:
            failures += 1

            raise TokenCommandError("Not signed in.")

        return "azr_signed_in"

    cache = TokenCache(run=failing_once, clock=Clock(NOW))

    with pytest.raises(TokenCommandError):
        cache.token(COMMAND)

    assert cache.token(COMMAND) == "azr_signed_in"


def test_a_command_that_is_not_one_is_refused_before_it_is_run() -> None:
    printing = Printing()
    cache = TokenCache(run=printing, clock=Clock(NOW))

    with pytest.raises(TokenCommandError):
        cache.token(())

    assert printing.runs == []


def test_forgetting_runs_every_command_again() -> None:
    printing = Printing("azr_first", "azr_second")
    cache = TokenCache(run=printing, clock=Clock(NOW))
    cache.token(COMMAND)

    cache.forget()

    assert cache.token(COMMAND) == "azr_second"

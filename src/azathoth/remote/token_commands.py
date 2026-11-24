"""The commands a named remote's token is printed by (ADR 0141).

A remote behind a single sign-on proxy, or one whose policy accepts an
identity provider's tokens, is reached with a token that lasts an hour or
so, which no variable keeps fresh. A named remote may instead name a
command that prints one, as `gcloud auth print-identity-token` does, and
it is run whenever the remote is reached and no token it printed is kept.

A command is its arguments, run as they are, never through a shell. It is
given no input, and has `TOKEN_COMMAND_TIMEOUT_SECONDS` to print the token
alone on standard output; what it says on standard error is shown when it
fails. Its token is kept in this process only, never written down: until
`TOKEN_REFRESH_MARGIN_SECONDS` before the expiry a JWT names, or for
`OPAQUE_TOKEN_SECONDS` when it is not a JWT. A JWT's claims are only read
for when it expires; the remote is what checks its signature.
"""

import base64
import binascii
import json
import shlex
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from typing import Final

TOKEN_COMMAND_TIMEOUT_SECONDS: Final = 30.0
"""How long a token command has to print the token."""

TOKEN_REFRESH_MARGIN_SECONDS: Final = 30.0
"""How long before a JWT's expiry its command is run again, so no call sends it expired."""

OPAQUE_TOKEN_SECONDS: Final = 300.0
"""How long a token naming no expiry is kept before its command is run again."""

MAX_ERROR_SHOWN: Final = 500
"""How many characters of what a failing command said on standard error are shown, its end."""

EMPTY_COMMAND_MESSAGE: Final = (
    "A token command names the program that prints the token; it was empty."
)

NUL_COMMAND_MESSAGE: Final = "A token command's arguments may not hold a NUL character."

ONE_STRING_MESSAGE: Final = (
    "A token command is given as its arguments, not as one string: split it as a shell would, "
    "as shlex.split does."
)


class TokenCommandError(ValueError):
    """A token command is not one, or did not print a token."""


def require_token_command(
    command: Sequence[str],
) -> tuple[str, ...]:
    """Return a token command as its arguments, or refuse one that cannot be run.

    Raises:
        TokenCommandError: The command is one string rather than its
            arguments, names no program, or an argument holds a NUL.
    """

    if isinstance(command, str):
        raise TokenCommandError(ONE_STRING_MESSAGE)

    arguments = tuple(command)

    if not arguments or arguments[0] == "":
        raise TokenCommandError(EMPTY_COMMAND_MESSAGE)

    if any("\0" in argument for argument in arguments):
        raise TokenCommandError(NUL_COMMAND_MESSAGE)

    return arguments


def shown_command(
    command: Sequence[str],
) -> str:
    """Return a token command as a shell would read it, each argument quoted where it must be."""

    return shlex.join(command)


def _said(
    stderr: str,
) -> str:
    """Return what a command said on standard error, on one line, its end kept."""

    said = " ".join(stderr.split())

    return said if len(said) <= MAX_ERROR_SHOWN else "…" + said[-MAX_ERROR_SHOWN:]


def printed_token(
    command: Sequence[str],
    *,
    timeout: float = TOKEN_COMMAND_TIMEOUT_SECONDS,
) -> str:
    """Run a token command, and return the token it printed.

    Raises:
        TokenCommandError: The command is not one, could not be run, ran
            longer than `timeout` seconds, exited with a status other than
            0, or printed no token or more than one.
    """

    arguments = require_token_command(command)
    shown = shown_command(arguments)

    try:
        completed = subprocess.run(
            arguments,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        raise TokenCommandError(
            f"Token command `{shown}` could not be run: {arguments[0]} was not found."
        ) from None
    except subprocess.TimeoutExpired:
        raise TokenCommandError(
            f"Token command `{shown}` printed no token within {timeout:g} seconds."
        ) from None
    except OSError as exc:
        raise TokenCommandError(
            f"Token command `{shown}` could not be run: {exc.strerror or exc}."
        ) from None

    if completed.returncode != 0:
        said = _said(completed.stderr)

        raise TokenCommandError(
            f"Token command `{shown}` exited with status {completed.returncode}"
            + (f": {said}" if said else ", saying nothing on standard error.")
        )

    token = completed.stdout.strip()

    if not token:
        raise TokenCommandError(f"Token command `{shown}` printed no token.")

    if any(character.isspace() for character in token):
        raise TokenCommandError(
            f"Token command `{shown}` printed more than a token: it must print the token "
            "alone, on one line."
        )

    return token


def expires_at(
    token: str,
) -> float | None:
    """Return when a JWT expires, in seconds since the epoch, or None for any other token.

    Only the claims are read, for `exp`; nothing is verified, since the
    remote checks the token, and this only says how long to keep it.
    """

    parts = token.split(".")

    if len(parts) != 3:
        return None

    payload = parts[1]

    try:
        claims: object = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (binascii.Error, ValueError):
        return None

    expiry = claims.get("exp") if isinstance(claims, dict) else None

    if isinstance(expiry, bool) or not isinstance(expiry, int | float):
        return None

    return float(expiry)


class TokenCache:
    """The tokens token commands printed, each kept until shortly before it expires.

    `run` runs a command and returns its token, and `clock` says the time in
    seconds since the epoch, as tests replace them. A command is run by one
    caller at a time, so callers asking at once wait for one run rather than
    each running it.
    """

    def __init__(
        self,
        *,
        run: Callable[[tuple[str, ...]], str] = printed_token,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._run = run
        self._clock = clock
        self._lock = threading.Lock()
        self._held: dict[tuple[str, ...], tuple[str, float]] = {}

    def token(
        self,
        command: Sequence[str],
    ) -> str:
        """Return the token a command prints, running it unless one it printed is still kept.

        Raises:
            TokenCommandError: The command is not one, or printed no token.
        """

        arguments = require_token_command(command)

        with self._lock:
            now = self._clock()
            held = self._held.get(arguments)

            if held is not None and now < held[1]:
                return held[0]

            self._held.pop(arguments, None)
            token = self._run(arguments)
            expiry = expires_at(token)
            self._held[arguments] = (
                token,
                now + OPAQUE_TOKEN_SECONDS
                if expiry is None
                else expiry - TOKEN_REFRESH_MARGIN_SECONDS,
            )

            return token

    def forget(
        self,
    ) -> None:
        """Forget every token kept, so each command is run again when next asked."""

        with self._lock:
            self._held.clear()


TOKEN_COMMANDS: Final = TokenCache()
"""The tokens this process's token commands printed."""


def command_token(
    command: Sequence[str],
) -> str:
    """Return the token a command prints, kept in this process until shortly before it expires.

    Raises:
        TokenCommandError: The command is not one, or printed no token.
    """

    return TOKEN_COMMANDS.token(command)


__all__ = [
    "MAX_ERROR_SHOWN",
    "OPAQUE_TOKEN_SECONDS",
    "TOKEN_COMMANDS",
    "TOKEN_COMMAND_TIMEOUT_SECONDS",
    "TOKEN_REFRESH_MARGIN_SECONDS",
    "TokenCache",
    "TokenCommandError",
    "command_token",
    "expires_at",
    "printed_token",
    "require_token_command",
    "shown_command",
]

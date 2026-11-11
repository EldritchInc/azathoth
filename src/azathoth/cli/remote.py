"""Remote commands for the Azathoth command-line application (ADR 0124).

Tokens are durable state of the database a remote serves, so these
commands read and write only that database: no runtime is loaded, and no
provider credentials are needed.
"""

import sys

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.service import current_author
from azathoth.remote import RemoteToken, RemoteTokenError

TOKEN_SHOWN_ONCE_NOTE = (
    "Keep the token now: this remote keeps only its digest, and cannot show it again."
)
"""What `remote token create` says after the token it shows."""


def create_remote_token(
    name: str,
) -> int:
    """Create a token under a name, recording who created it, and show it once."""

    author = current_author()

    if author is None:
        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        issued = repositories(configuration).remote_tokens.create(name, author=author)
    except RemoteTokenError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(f"Created remote token {issued.token.name}.")
    print(f"Token: {issued.secret}")
    print(TOKEN_SHOWN_ONCE_NOTE)

    return 0


def list_remote_tokens(
    *,
    include_revoked: bool = False,
) -> int:
    """List the active tokens, or every token, oldest first, one per line."""

    configuration = CliRuntimeConfiguration.from_environment()

    for token in repositories(configuration).remote_tokens.tokens(
        include_revoked=include_revoked,
    ):
        print(token_line(token))

    return 0


def revoke_remote_token(
    name: str,
) -> int:
    """Revoke the active token of a name, so it no longer reaches this remote."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        revoked = repositories(configuration).remote_tokens.revoke(name)
    except RemoteTokenError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(f"Revoked remote token {revoked.name}.")

    return 0


def token_line(
    token: RemoteToken,
) -> str:
    """Return one token's line: its name, when it was created and by whom, and any revocation."""

    author = "" if token.author is None else f"  by {token.author}"
    revoked = "" if token.revoked_at is None else f"  revoked {token.revoked_at.isoformat()}"

    return f"{token.name}  {token.created_at.isoformat()}{author}{revoked}"


__all__ = [
    "TOKEN_SHOWN_ONCE_NOTE",
    "create_remote_token",
    "list_remote_tokens",
    "revoke_remote_token",
    "token_line",
]

"""Remote commands for the Azathoth command-line application (ADR 0124).

A remote serves durable documents, and tokens are durable state of the
database it serves, so these commands read and write only that database:
no runtime is loaded, and no provider credentials are needed.
"""

import sys

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.service import current_author
from azathoth.remote import (
    MISSING_REMOTE_EXTRA_MESSAGE,
    PROTOCOL_VERSION,
    RemotePluginError,
    RemoteToken,
    RemoteTokenError,
    TokenAuthenticator,
    load_seams,
)

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


def serving_line(
    url: str,
    *,
    accept_restricted: bool,
) -> str:
    """Return the line `remote serve` starts with: where, and whether it takes restricted data."""

    restricted = "accepts restricted data" if accept_restricted else "refuses restricted data"

    return f"Serving remote protocol {PROTOCOL_VERSION} at {url}; it {restricted}."


def serve_remote(
    *,
    host: str,
    port: int,
    accept_restricted: bool = False,
) -> int:
    """Serve this instance as a remote with uvicorn, until stopped.

    The `remote` extra must be installed, and the plugins installed for the
    remote's seams must be ones it can use; otherwise nothing is served,
    and the reason is printed.
    """

    try:
        from uvicorn import run as run_uvicorn

        from azathoth.remote.server import RemoteServer
    except ImportError:
        print(MISSING_REMOTE_EXTRA_MESSAGE, file=sys.stderr)

        return 1

    configuration = CliRuntimeConfiguration.from_environment()
    held = repositories(configuration)

    try:
        seams = load_seams(default_authenticator=TokenAuthenticator(held.remote_tokens))
    except RemotePluginError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    server = RemoteServer(
        workflows=held.workflows,
        tools=held.tools,
        benchmarks=held.benchmarks,
        content=held.content,
        seams=seams,
        accepts_restricted=accept_restricted,
    )

    print(
        serving_line(f"http://{host}:{port}", accept_restricted=accept_restricted),
        file=sys.stderr,
    )
    run_uvicorn(server.app(), host=host, port=port, log_level="info")

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
    "serve_remote",
    "serving_line",
    "token_line",
]

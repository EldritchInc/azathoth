"""Remote commands for the Azathoth command-line application (ADR 0124, ADR 0126).

A remote serves durable documents, and tokens are durable state of the
database it serves, as the names an instance gives remotes are of its own,
so these commands read and write only that database: no runtime is loaded,
and no provider credentials are needed.
"""

import sys
from collections.abc import Sequence
from uuid import UUID

from azathoth import api
from azathoth.api.remote import reach
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.service import current_author
from azathoth.remote import (
    MISSING_REMOTE_EXTRA_MESSAGE,
    PROTOCOL_VERSION,
    REMOTE_TOKEN_VARIABLE,
    NamedRemote,
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
        production_states=held.production_states,
        portfolio=held.portfolio,
        seams=seams,
        accepts_restricted=accept_restricted,
    )

    print(
        serving_line(f"http://{host}:{port}", accept_restricted=accept_restricted),
        file=sys.stderr,
    )
    run_uvicorn(server.app(), host=host, port=port, log_level="info")

    return 0


def tool_versions(
    named: Sequence[str],
) -> tuple[tuple[UUID, str], ...]:
    """Return the tool versions named as `TOOL_ID@VERSION`.

    Raises:
        ValueError: One is not a tool ID and a version.
    """

    versions: list[tuple[UUID, str]] = []

    for value in named:
        tool_id, separator, version = value.partition("@")

        try:
            parsed = UUID(tool_id)
        except ValueError:
            parsed = None

        if parsed is None or not separator or not version:
            raise ValueError(f"Tool {value!r} is not <TOOL_ID>@<VERSION>.")

        versions.append((parsed, version))

    return tuple(versions)


def _remote(
    target: str,
) -> api.Remote:
    """Return the remote a name or URL names, over the configured database's repositories.

    Raises:
        InvalidArgumentError: The URL is not one, or no token is set.
        NotFoundError: No remote has the name.
    """

    held = repositories(CliRuntimeConfiguration.from_environment())

    return reach(target, lambda: held)


def _remotes() -> api.Remotes:
    """Return the remotes the configured database names."""

    held = repositories(CliRuntimeConfiguration.from_environment())

    return api.Remotes(lambda: held)


def named_line(
    remote: NamedRemote,
) -> str:
    """Return one named remote's line: its name, its URL and its token's variable."""

    return f"{remote.name}  {remote.url}  {remote.token_variable}"


def add_remote(
    *,
    name: str,
    url: str,
    token_variable: str = REMOTE_TOKEN_VARIABLE,
) -> int:
    """Name the remote at a URL, its token read from a variable, so commands can name it."""

    try:
        added = _remotes().add(name, url, token_variable=token_variable)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(
        f"Named remote {added.name} for {added.url}; its token is read from {added.token_variable}."
    )

    return 0


def list_remotes() -> int:
    """List the remotes this instance names, by name, one per line."""

    for remote in _remotes().list():
        print(named_line(remote))

    return 0


def remove_remote(
    name: str,
) -> int:
    """Forget a remote's name, and the last portfolio read from it; nothing there changes."""

    try:
        removed = _remotes().remove(name)
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(f"Removed remote {removed.name}, for {removed.url}; nothing at the remote changed.")

    return 0


def push_to_remote(
    *,
    remote: str,
    workflows: Sequence[UUID] = (),
    tools: Sequence[str] = (),
    benchmarks: Sequence[UUID] = (),
) -> int:
    """Push the documents named, with what they need, to the remote a name or URL names.

    What would stop them from running there is warned of on standard error,
    after the report; a warning never refuses the push (ADR 0125).
    """

    try:
        report = _remote(remote).push(
            workflows=workflows,
            tools=tool_versions(tools),
            benchmarks=benchmarks,
        )
    except (api.ApiError, ValueError) as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(
        f"Pushed to {report.remote}. Revisions received: {len(report.received)}. Revisions "
        f"already held: {report.already_held}. Content sent: {report.content_sent}."
    )

    for saved in report.received:
        print(f"Received {saved.lineage} as revision {saved.number}.")

    for unresolved in report.unresolved:
        print(f"Not gathered: {unresolved}")

    for warning in report.warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    return 0


def pull_from_remote(
    *,
    remote: str,
    workflows: Sequence[UUID] = (),
    tools: Sequence[str] = (),
    benchmarks: Sequence[UUID] = (),
    include_restricted: bool = False,
) -> int:
    """Pull the documents named, with what they need, from the remote a name or URL names."""

    try:
        report = _remote(remote).pull(
            workflows=workflows,
            tools=tool_versions(tools),
            benchmarks=benchmarks,
            include_restricted=include_restricted,
        )
    except (api.ApiError, ValueError) as exc:
        print(str(exc), file=sys.stderr)

        return 1

    print(
        f"Pulled from {report.remote}. Revisions saved: {len(report.received)}. Revisions "
        f"already held: {report.already_held}. Content fetched: {report.content_fetched}."
    )

    for saved in report.received:
        print(f"Saved {saved.lineage} as revision {saved.number}.")

    for lineage in report.forked:
        print(f"Forked {lineage}: its pulled revisions build on an earlier revision here.")

    for lineage in report.withheld:
        print(f"Withheld {lineage}: it is restricted; pull it with --include-restricted.")

    for unresolved in report.unresolved:
        print(f"Not gathered at the remote: {unresolved}")

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
    "add_remote",
    "create_remote_token",
    "list_remote_tokens",
    "list_remotes",
    "named_line",
    "pull_from_remote",
    "push_to_remote",
    "remove_remote",
    "revoke_remote_token",
    "serve_remote",
    "serving_line",
    "token_line",
    "tool_versions",
]

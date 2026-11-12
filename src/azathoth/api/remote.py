"""Pushing to and pulling from a remote through the service API (ADR 0124).

`instance.remote(url)` names a remote, by its URL or by a name
`instance.remotes` gave it (ADR 0126); each call reaches it afresh, with
the token given, or the one in its token variable, `AZATHOTH_REMOTE_TOKEN`
unless the name says another. A push sends the
latest revision of each document named, the revisions it was reached by,
and what it needs at the remote; a pull brings the same back, forking a
lineage that diverged here; a status compares the two sides (ADR 0125).
"""

import os
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from uuid import UUID

from azathoth.api.browsing import RepositoriesAccess
from azathoth.api.errors import (
    ConflictError,
    InvalidArgumentError,
    NotFoundError,
    RemoteDivergedError,
    RemoteProtocolError,
    RemoteRefusedError,
    RemoteUnreachableError,
)
from azathoth.remote import (
    REMOTE_TOKEN_VARIABLE,
    Capabilities,
    HttpClient,
    NamedRemote,
    ProtocolMismatchError,
    PullReport,
    PushReport,
    ReceiveRefusedError,
    RemoteAlreadyNamedError,
    RemoteClient,
    RemoteNameError,
    RemoteNotNamedError,
    RemoteStatus,
    pull_from,
    push_to,
    require_remote_url,
    status_of,
)
from azathoth.remote import RemoteDivergedError as ClientDivergedError
from azathoth.remote import RemoteRefusedError as ClientRefusedError
from azathoth.remote import RemoteUnreachableError as ClientUnreachableError
from azathoth.revisions import Lineage, RevisionKind


def no_token_message(
    variable: str,
) -> str:
    """Return what reaching a remote says when no token is given and its variable is not set."""

    return (
        f"No remote token was given; set {variable} to one created on the remote with "
        "`azathoth remote token create`."
    )


NO_TOKEN_MESSAGE = no_token_message(REMOTE_TOKEN_VARIABLE)
"""What naming a remote by its URL without a token says."""


def is_remote_url(
    target: str,
) -> bool:
    """Return whether a remote is named by its URL, not by a name given it.

    A name holds no `:`, `/` or `.`, so anything that does is read as a URL,
    and refused if it is not an http or https one; a bare host is refused so
    too, rather than looked up as a name.
    """

    return any(character in target for character in ":/.")


def not_named_message(
    name: str,
) -> str:
    """Return what reaching, or removing, a name no remote has says."""

    return f"No remote is named {name!r}; name one with `azathoth remote add <NAME> <URL>`."


def lineages(
    *,
    workflows: Sequence[UUID],
    tools: Sequence[tuple[UUID, str]],
    benchmarks: Sequence[UUID],
    required: bool = True,
) -> tuple[Lineage, ...]:
    """Return the lineages of the workflows, tool versions and benchmarks named, in that order.

    Raises:
        InvalidArgumentError: Nothing is named, and something is `required`.
    """

    named = (
        *(Lineage(kind=RevisionKind.WORKFLOW, id=workflow_id) for workflow_id in workflows),
        *(
            Lineage(kind=RevisionKind.TOOL, id=tool_id, version=version)
            for tool_id, version in tools
        ),
        *(Lineage(kind=RevisionKind.BENCHMARK, id=benchmark_id) for benchmark_id in benchmarks),
    )

    if required and not named:
        raise InvalidArgumentError("Name a workflow, tool version or benchmark to send.")

    return named


class Remote:
    """One remote this instance pushes to and pulls from."""

    def __init__(
        self,
        url: str,
        repositories: RepositoriesAccess,
        *,
        token: str | None = None,
        token_variable: str = REMOTE_TOKEN_VARIABLE,
        name: str | None = None,
        http: Callable[[], HttpClient] | None = None,
    ) -> None:
        """Name the remote at `url`, reached with `token`, or the one `token_variable` holds.

        `name` is the name this instance gave it, if it was reached by one.
        `http`, when given, makes the HTTP client each call is sent over, as
        tests do.

        Raises:
            InvalidArgumentError: The URL is not an http or https URL, or no
                token is given or set.
        """

        try:
            self._url = require_remote_url(url)
        except ValueError as exc:
            raise InvalidArgumentError(str(exc)) from None

        given = token if token is not None else os.environ.get(token_variable)

        if not given:
            raise InvalidArgumentError(no_token_message(token_variable))

        self._token = given
        self._name = name
        self._repositories = repositories
        self._http = http

    @property
    def url(
        self,
    ) -> str:
        """Return the remote's URL."""

        return self._url

    @property
    def name(
        self,
    ) -> str | None:
        """Return the name this instance gave the remote, or None when it was reached by URL."""

        return self._name

    def capabilities(
        self,
    ) -> Capabilities:
        """Return what the remote is: its protocol, versions, edition, plugins, and restricted data.

        Raises:
            RemoteUnreachableError: The remote was not reached.
            RemoteRefusedError: The remote refused the token.
        """

        with self._client() as client:
            return client.capabilities()

    def push(
        self,
        *,
        workflows: Sequence[UUID] = (),
        tools: Sequence[tuple[UUID, str]] = (),
        benchmarks: Sequence[UUID] = (),
    ) -> PushReport:
        """Push the documents named, with what they need, sending only what the remote lacks.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: Nothing is named.
            RemoteProtocolError: The remote speaks another protocol.
            RemoteDivergedError: A lineage diverged at the remote; pull first.
            RemoteRefusedError: The remote refused the push, as restricted
                data it does not accept.
            RemoteUnreachableError: The remote was not reached.
        """

        roots = lineages(workflows=workflows, tools=tools, benchmarks=benchmarks)
        held = self._repositories()

        with self._client() as client:
            return push_to(
                client,
                roots,
                workflows=held.workflows,
                tools=held.tools,
                benchmarks=held.benchmarks,
                content=held.content,
            )

    def pull(
        self,
        *,
        workflows: Sequence[UUID] = (),
        tools: Sequence[tuple[UUID, str]] = (),
        benchmarks: Sequence[UUID] = (),
        include_restricted: bool = False,
    ) -> PullReport:
        """Pull the documents named, with what they need, saving what is not held here.

        A lineage that diverged here is forked on the revision the pulled
        revisions build on, and named in the report. A restricted benchmark
        comes only with `include_restricted`; otherwise it is named as
        withheld.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: Nothing is named.
            RemoteProtocolError: The remote speaks another protocol.
            RemoteRefusedError: The remote refused the pull, or what it sent
                cannot be kept here.
            RemoteUnreachableError: The remote was not reached.
        """

        roots = lineages(workflows=workflows, tools=tools, benchmarks=benchmarks)
        held = self._repositories()

        with self._client() as client:
            return pull_from(
                client,
                roots,
                include_restricted=include_restricted,
                workflows=held.workflows,
                tools=held.tools,
                benchmarks=held.benchmarks,
                content=held.content,
            )

    def status(
        self,
        *,
        workflows: Sequence[UUID] = (),
        tools: Sequence[tuple[UUID, str]] = (),
        benchmarks: Sequence[UUID] = (),
    ) -> RemoteStatus:
        """Return how the documents named, or every one either side holds, relate (ADR 0125).

        Each component says how this instance's latest revision relates to
        the remote's: in sync, ahead, behind, diverged, or held by one side
        only; a workflow says which revision is in production at the remote.
        Each model says whether it is authorized here and at the remote.
        Reaching the remote refreshes the snapshot of its portfolio. A remote
        that cannot be reached is no error: its side is unknown, each
        relation is None, and its models are read from the last snapshot,
        as of `portfolio_synced_at`.

        Raises:
            InstanceClosedError: The instance was closed.
            RemoteProtocolError: The remote speaks another protocol.
            RemoteRefusedError: The remote refused the token or a request.
        """

        roots = lineages(
            workflows=workflows,
            tools=tools,
            benchmarks=benchmarks,
            required=False,
        )
        held = self._repositories()

        with self._client() as client:
            return status_of(
                client,
                roots,
                workflows=held.workflows,
                tools=held.tools,
                benchmarks=held.benchmarks,
                production_states=held.production_states,
                portfolio=held.portfolio,
                snapshots=held.remote_portfolio_snapshots,
            )

    @contextmanager
    def _client(
        self,
    ) -> Iterator[RemoteClient]:
        """Reach the remote for one call, raising what goes wrong as the service API's errors."""

        try:
            with RemoteClient(
                self._url,
                self._token,
                http=None if self._http is None else self._http(),
            ) as client:
                yield client
        except ClientDivergedError as exc:
            raise RemoteDivergedError(str(exc)) from exc
        except (ClientRefusedError, ReceiveRefusedError) as exc:
            raise RemoteRefusedError(str(exc)) from exc
        except ClientUnreachableError as exc:
            raise RemoteUnreachableError(str(exc)) from exc
        except ProtocolMismatchError as exc:
            raise RemoteProtocolError(str(exc)) from exc


class Remotes:
    """The remotes this instance names, so a call can say `origin` for its URL (ADR 0126)."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
    ) -> None:
        """Keep the remotes the repositories `repositories` returns name."""

        self._repositories = repositories

    def list(
        self,
    ) -> tuple[NamedRemote, ...]:
        """Return every remote named, ordered by name.

        Raises:
            InstanceClosedError: The instance was closed.
        """

        return self._repositories().remotes.remotes()

    def get(
        self,
        name: str,
    ) -> NamedRemote:
        """Return the remote of a name.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No remote has the name.
        """

        named = self._repositories().remotes.get(name)

        if named is None:
            raise NotFoundError(not_named_message(name))

        return named

    def add(
        self,
        name: str,
        url: str,
        *,
        token_variable: str = REMOTE_TOKEN_VARIABLE,
    ) -> NamedRemote:
        """Name the remote at `url`, its token read from `token_variable`, and return it.

        Only the variable's name is kept, never a token.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The name, URL or variable is not one.
            ConflictError: A remote already has the name.
        """

        try:
            return self._repositories().remotes.add(name, url, token_variable=token_variable)
        except RemoteAlreadyNamedError as exc:
            raise ConflictError(str(exc)) from None
        except RemoteNameError as exc:
            raise InvalidArgumentError(str(exc)) from None

    def remove(
        self,
        name: str,
    ) -> NamedRemote:
        """Forget a name, and return the remote it named.

        The last portfolio read from the remote is forgotten too, unless
        another name is kept for its URL. Nothing at the remote changes.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No remote has the name.
        """

        held = self._repositories()

        try:
            removed = held.remotes.remove(name)
        except RemoteNotNamedError:
            raise NotFoundError(not_named_message(name)) from None

        if all(other.url != removed.url for other in held.remotes.remotes()):
            held.remote_portfolio_snapshots.delete(removed.url)

        return removed


def reach(
    target: str,
    repositories: RepositoriesAccess,
    *,
    token: str | None = None,
    http: Callable[[], HttpClient] | None = None,
) -> Remote:
    """Return the remote a URL, or a name this instance gave it, names.

    A named remote's token is read from its own variable, unless `token` is
    given.

    Raises:
        InstanceClosedError: The instance was closed.
        InvalidArgumentError: The URL is not an http or https URL, or no
            token is given or set.
        NotFoundError: No remote has the name.
    """

    if is_remote_url(target):
        return Remote(target, repositories, token=token, http=http)

    named = Remotes(repositories).get(target)

    return Remote(
        named.url,
        repositories,
        token=token,
        token_variable=named.token_variable,
        name=named.name,
        http=http,
    )


__all__ = [
    "NO_TOKEN_MESSAGE",
    "Remote",
    "Remotes",
    "is_remote_url",
    "lineages",
    "no_token_message",
    "not_named_message",
    "reach",
]

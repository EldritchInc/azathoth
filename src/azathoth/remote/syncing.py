"""Pushing to, pulling from and comparing with a remote, for a local instance (ADR 0124).

A push asks the remote what it lacks, sends that content, then the missing
revisions, parents first. A pull asks for documents, fetches the content
the bundle's benchmarks hold that is not here, and saves the revisions not
held, forking a lineage that diverged here. Both read the remote's
capabilities first, and refuse another protocol before sending anything.
"""

from collections.abc import Iterable, Mapping, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from azathoth.evaluation import BenchmarkRepository
from azathoth.inputs import ContentStore
from azathoth.providers import ModelPortfolioRepository
from azathoth.remote.client import RemoteClient, RemoteRefusedError, RemoteUnreachableError
from azathoth.remote.closure import child_workflow_id, closure, lineage_records
from azathoth.remote.inspection import heads
from azathoth.remote.receiving import (
    ReceivedRevision,
    ReceiveRefusedError,
    receive,
    receive_content,
    restricted_refusal,
)
from azathoth.remote.records import (
    CredentialsRequest,
    Head,
    HeadsRequest,
    MissingRequest,
    PullRequest,
    PushBundle,
)
from azathoth.remote.snapshots import PortfolioSnapshot, RemotePortfolioSnapshotRepository
from azathoth.remote.status import (
    ComponentStatus,
    ModelStatus,
    RemoteStatus,
    child_drift_warnings,
    credential_names,
    fixed_models,
    missing_credential_warning,
    relation,
    unapproved_model_warnings,
)
from azathoth.revisions import Lineage, RevisionKind
from azathoth.sensitivity import Sensitivity
from azathoth.tools import ToolRepository
from azathoth.workflows import (
    WorkflowProductionStateRepository,
    WorkflowRepository,
    WorkflowSpecification,
)


class PushReport(BaseModel):
    """What a push sent, what the remote received, what could not be sent, and what to fix there.

    `warnings` name what would stop the pushed documents from running at the
    remote (ADR 0125); a warning never refuses a push.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    remote: str

    received: tuple[ReceivedRevision, ...] = ()

    already_held: int = 0

    content_sent: int = 0

    unresolved: tuple[str, ...] = ()

    warnings: tuple[str, ...] = ()


class PullReport(BaseModel):
    """What a pull saved, what it held already, forked or was not sent, and why."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    remote: str

    received: tuple[ReceivedRevision, ...] = ()

    already_held: int = 0

    content_fetched: int = 0

    forked: tuple[Lineage, ...] = ()

    withheld: tuple[Lineage, ...] = ()

    unresolved: tuple[str, ...] = ()


def push_to(
    client: RemoteClient,
    roots: Iterable[Lineage],
    *,
    workflows: WorkflowRepository,
    tools: ToolRepository,
    benchmarks: BenchmarkRepository,
    content: ContentStore,
) -> PushReport:
    """Push some documents, with what they need, to a remote, sending only what it lacks.

    Raises:
        ProtocolMismatchError: The remote speaks another protocol.
        RemoteRefusedError: The push holds restricted data the remote does
            not accept, or the remote refused a request.
        RemoteUnreachableError: The remote was not reached.
        ReceiveRefusedError: Content a pushed benchmark holds is not held
            here.
    """

    capabilities = client.capabilities().require_protocol()
    gathered = closure(roots, workflows=workflows, tools=tools, benchmarks=benchmarks)
    bundle = PushBundle(revisions=gathered.revisions, content=gathered.content)

    if bundle.sensitivity is Sensitivity.RESTRICTED and not capabilities.accepts_restricted:
        raise RemoteRefusedError(restricted_refusal("This push carries restricted data"))

    lacking = client.missing(
        MissingRequest(
            lineages=tuple(dict.fromkeys(record.lineage for record in bundle.revisions)),
            revisions=tuple(record.revision_digest for record in bundle.revisions),
            content=tuple(record.digest for record in bundle.content),
        )
    )
    labels = {record.digest: record.sensitivity for record in bundle.content}

    for digest in lacking.content:
        data = content.get(digest)

        if data is None:
            raise ReceiveRefusedError(
                f"Content {digest}, which a pushed benchmark holds, is not held here."
            )

        client.put_content(digest, data, sensitivity=labels[digest])

    wanted = set(lacking.revisions)
    revisions = tuple(record for record in bundle.revisions if record.revision_digest in wanted)
    received = (
        client.push(PushBundle(revisions=revisions, content=bundle.content)) if revisions else None
    )

    return PushReport(
        remote=client.url,
        received=() if received is None else received.received,
        already_held=len(bundle.revisions)
        - len(revisions)
        + (0 if received is None else received.already_held),
        content_sent=len(lacking.content),
        unresolved=gathered.unresolved,
        warnings=push_warnings(client, bundle, workflows=workflows, tools=tools),
    )


def push_warnings(
    client: RemoteClient,
    bundle: PushBundle,
    *,
    workflows: WorkflowRepository,
    tools: ToolRepository,
) -> tuple[str, ...]:
    """Return what would stop a push's documents from running at the remote, once pushed.

    Credentials the pushed tools need that the remote does not set come
    first, then child workflows the remote runs at another revision or not
    at all, then models the pushed workflows' steps fix that the remote has
    not authorized. Only names are sent to ask; no credential's value is.
    """

    pushed = tuple(dict.fromkeys(record.lineage for record in bundle.revisions))
    needs: dict[str, list[Lineage]] = {}

    for lineage in pushed:
        if lineage.kind is not RevisionKind.TOOL or lineage.version is None:
            continue

        revision = tools.latest_document_revision(lineage.id, lineage.version)

        for name in () if revision is None else credential_names(revision.document):
            needs.setdefault(name, []).append(lineage)

    warnings: list[str] = []

    if needs:
        unset = client.missing_credentials(CredentialsRequest(names=tuple(needs))).missing
        warnings.extend(
            missing_credential_warning(lineage, name) for name in unset for lineage in needs[name]
        )

    specifications: list[WorkflowSpecification] = []

    for lineage in pushed:
        specification = workflows.get(lineage.id) if lineage.kind is RevisionKind.WORKFLOW else None

        if specification is not None:
            specifications.append(specification)

    children: dict[Lineage, None] = {}

    for specification in specifications:
        for step in specification.steps:
            child = child_workflow_id(step)

            if isinstance(child, UUID):
                children[Lineage(kind=RevisionKind.WORKFLOW, id=child)] = None

    if children:
        running = {
            head.lineage.id: head.production_digest
            for head in client.heads(HeadsRequest(lineages=tuple(children))).heads
        }
        latest: dict[UUID, str] = {}

        for child_lineage in children:
            records = workflows.lineage(child_lineage.id)

            if records:
                latest[child_lineage.id] = records[-1].revision_digest

        for specification in specifications:
            warnings.extend(
                child_drift_warnings(
                    specification,
                    local_latest=latest,
                    remote_production=running,
                )
            )

    if any(tuple(fixed_models(specification)) for specification in specifications):
        authorized = {entry.identifier for entry in client.portfolio().entries}

        for specification in specifications:
            warnings.extend(unapproved_model_warnings(specification, authorized=authorized))

    return tuple(warnings)


def pull_from(
    client: RemoteClient,
    roots: Iterable[Lineage],
    *,
    include_restricted: bool,
    workflows: WorkflowRepository,
    tools: ToolRepository,
    benchmarks: BenchmarkRepository,
    content: ContentStore,
) -> PullReport:
    """Pull some documents, with what they need, from a remote, saving what is not held.

    A lineage that diverged here is forked on the revision the pulled
    revisions build on. Restricted benchmarks come only with
    `include_restricted`.

    Raises:
        ProtocolMismatchError: The remote speaks another protocol.
        RemoteRefusedError: The remote refused a request.
        RemoteUnreachableError: The remote was not reached.
        ReceiveRefusedError: Fetched content is not its digest, or a pulled
            revision cannot be saved here.
    """

    client.capabilities().require_protocol()
    asked = tuple(dict.fromkeys(roots))
    held = tuple(
        record.revision_digest
        for root in asked
        for record in lineage_records(root, workflows=workflows, tools=tools, benchmarks=benchmarks)
    )
    answer = client.pull(PullRequest(roots=asked, held=held, include_restricted=include_restricted))
    fetched = 0

    for record in answer.bundle.content:
        if content.contains(record.digest):
            continue

        receive_content(
            content,
            client.get_content(record.digest),
            digest=record.digest,
            sensitivity=record.sensitivity,
            accepts_restricted=True,
        )
        fetched += 1

    report = receive(
        answer.bundle,
        workflows=workflows,
        tools=tools,
        benchmarks=benchmarks,
        content=content,
        accepts_restricted=True,
        fork=True,
    )

    return PullReport(
        remote=client.url,
        received=report.received,
        already_held=report.already_held,
        content_fetched=fetched,
        forked=report.forked,
        withheld=answer.withheld,
        unresolved=answer.unresolved,
    )


def _order(
    asked: Sequence[Lineage],
    local: Mapping[Lineage, Head],
    remote: Mapping[Lineage, Head],
) -> tuple[Lineage, ...]:
    """Return the lineages a status reports: those asked about, or every one either side holds."""

    if asked:
        return tuple(lineage for lineage in asked if lineage in local or lineage in remote)

    return tuple(dict.fromkeys((*local, *remote)))


def _component(
    lineage: Lineage,
    local: Head | None,
    remote: Head | None,
    *,
    reachable: bool,
) -> ComponentStatus:
    """Return one component's status from each side's head."""

    return ComponentStatus(
        lineage=lineage,
        relation=(
            relation(
                () if local is None else local.chain,
                () if remote is None else remote.chain,
            )
            if reachable
            else None
        ),
        local_digest=None if local is None else local.chain[-1],
        local_number=None if local is None else local.number,
        remote_digest=None if remote is None else remote.chain[-1],
        remote_number=None if remote is None else remote.number,
        remote_production_digest=None if remote is None else remote.production_digest,
    )


def status_of(
    client: RemoteClient,
    roots: Iterable[Lineage] = (),
    *,
    workflows: WorkflowRepository,
    tools: ToolRepository,
    benchmarks: BenchmarkRepository,
    production_states: WorkflowProductionStateRepository,
    portfolio: ModelPortfolioRepository,
    snapshots: RemotePortfolioSnapshotRepository,
) -> RemoteStatus:
    """Return how what this instance holds relates to what a remote holds (ADR 0125).

    With no roots, every lineage either side holds is reported, this
    instance's first. Models are this portfolio's, then the remote's, then
    those the reported workflows' steps fix, each marked authorized or not
    on each side. Reaching the remote refreshes the snapshot of its
    portfolio; when it cannot be reached, its side is unknown, and its
    models are read from the last snapshot.

    Raises:
        ProtocolMismatchError: The remote speaks another protocol.
        RemoteRefusedError: The remote refused the token or a request.
    """

    asked = tuple(dict.fromkeys(roots))
    request = HeadsRequest(lineages=asked)
    remote_heads: dict[Lineage, Head] = {}

    try:
        client.capabilities().require_protocol()
        remote_heads = {head.lineage: head for head in client.heads(request).heads}
        snapshot: PortfolioSnapshot | None = snapshots.save(client.url, client.portfolio())
        reachable = True
    except RemoteUnreachableError:
        snapshot = snapshots.get(client.url)
        reachable = False

    local_heads = {
        head.lineage: head
        for head in heads(
            request,
            workflows=workflows,
            tools=tools,
            benchmarks=benchmarks,
            production_states=production_states,
        ).heads
    }
    reported = _order(asked, local_heads, remote_heads)
    authorized_here = [entry.identifier for entry in portfolio.entries()]
    authorized_there = (
        None if snapshot is None else [entry.identifier for entry in snapshot.portfolio.entries]
    )
    fixed: list[str] = []

    for lineage in reported:
        if lineage.kind is RevisionKind.WORKFLOW:
            latest = workflows.get(lineage.id)

            if latest is not None:
                fixed.extend(identifier for _, identifier in fixed_models(latest))

    identifiers = dict.fromkeys((*authorized_here, *(authorized_there or ()), *fixed))

    return RemoteStatus(
        remote=client.url,
        reachable=reachable,
        components=tuple(
            _component(
                lineage,
                local_heads.get(lineage),
                remote_heads.get(lineage),
                reachable=reachable,
            )
            for lineage in reported
        ),
        models=tuple(
            ModelStatus(
                identifier=identifier,
                authorized_locally=identifier in authorized_here,
                authorized_remotely=(
                    None if authorized_there is None else identifier in authorized_there
                ),
            )
            for identifier in identifiers
        ),
        portfolio_synced_at=None if snapshot is None else snapshot.synced_at,
    )


__all__ = [
    "PullReport",
    "PushReport",
    "pull_from",
    "push_warnings",
    "push_to",
    "status_of",
]

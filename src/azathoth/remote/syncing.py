"""Pushing to and pulling from a remote, for a local instance (ADR 0124).

A push asks the remote what it lacks, sends that content, then the missing
revisions, parents first. A pull asks for documents, fetches the content
the bundle's benchmarks hold that is not here, and saves the revisions not
held, forking a lineage that diverged here. Both read the remote's
capabilities first, and refuse another protocol before sending anything.
"""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from azathoth.evaluation import BenchmarkRepository
from azathoth.inputs import ContentStore
from azathoth.remote.client import RemoteClient, RemoteRefusedError
from azathoth.remote.closure import closure, lineage_records
from azathoth.remote.receiving import (
    ReceivedRevision,
    ReceiveRefusedError,
    receive,
    receive_content,
    restricted_refusal,
)
from azathoth.remote.records import MissingRequest, PullRequest, PushBundle
from azathoth.revisions import Lineage
from azathoth.sensitivity import Sensitivity
from azathoth.tools import ToolRepository
from azathoth.workflows import WorkflowRepository


class PushReport(BaseModel):
    """What a push sent, what the remote received, and what could not be sent."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    remote: str

    received: tuple[ReceivedRevision, ...] = ()

    already_held: int = 0

    content_sent: int = 0

    unresolved: tuple[str, ...] = ()


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
    )


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


__all__ = [
    "PullReport",
    "PushReport",
    "pull_from",
    "push_to",
]

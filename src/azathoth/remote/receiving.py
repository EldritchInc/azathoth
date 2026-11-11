"""Saving the revisions a push or pull brings, checked against what is already held (ADR 0124).

Every record of a bundle is checked before anything is saved: that this
Azathoth reads its document as the content its digest names, that the
content its benchmark cases hold is here, and that each lineage's first new
revision builds on the latest one held. A remote is moved only forward: a
push whose lineage has diverged there is refused, so its author pulls first.
A pull saves a diverged lineage's revisions on the revision they build on,
which forks it here, and reports which lineages forked.

A revision already held is skipped, so sending the same bundle again
changes nothing. A repository that refuses a revision once the checks have
passed, as one holding a tool document whose artifact IDs belong to another
tool, leaves the revisions saved before it, each on its parent. Each
revision is numbered by the instance that saves it; its revision digest is
its identity everywhere.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict, ValidationError

from azathoth import __version__
from azathoth.evaluation import BenchmarkDataset, BenchmarkRepository
from azathoth.inputs import ContentStore, content_bytes_digest
from azathoth.remote.closure import content_refs, lineage_records
from azathoth.remote.protocol import MAX_CONTENT_BYTES
from azathoth.remote.records import PushBundle, RevisionRecord
from azathoth.revisions import Lineage, LineageRecord, RevisionKind, content_digest
from azathoth.sensitivity import Sensitivity
from azathoth.tools import ToolDocument, ToolRepository
from azathoth.workflows import WorkflowRepository, WorkflowSpecification

ACCEPT_RESTRICTED_HINT: Final = (
    "Its operator accepts it by starting the remote with "
    "`azathoth remote serve --accept-restricted`."
)
"""How a remote's operator lets it receive restricted data (ADR 0123)."""

READERS: Final[dict[RevisionKind, type[BaseModel]]] = {
    RevisionKind.WORKFLOW: WorkflowSpecification,
    RevisionKind.TOOL: ToolDocument,
    RevisionKind.BENCHMARK: BenchmarkDataset,
}
"""The model each kind of document is read as."""


class ReceiveRefusedError(ValueError):
    """A bundle or content cannot be received; nothing of it was saved."""


class DivergedError(ReceiveRefusedError):
    """A lineage's latest revision here is not the one a pushed revision builds on."""


class RestrictedReceiveRefusedError(ReceiveRefusedError):
    """Restricted data was sent to a remote that does not accept it."""


class ReceivedRevision(BaseModel):
    """One revision saved: its lineage, its identity, and the number it has here."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    lineage: Lineage

    revision_digest: str

    number: int


class ReceiveReport(BaseModel):
    """What receiving a bundle saved, what it already held, and which lineages it forked."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    received: tuple[ReceivedRevision, ...] = ()

    already_held: int = 0

    forked: tuple[Lineage, ...] = ()


def restricted_refusal(
    subject: str,
) -> str:
    """Return the refusal of restricted data by a remote that does not accept it."""

    return f"{subject}, and this remote does not accept restricted data. {ACCEPT_RESTRICTED_HINT}"


def receive_content(
    store: ContentStore,
    data: bytes,
    *,
    digest: str,
    sensitivity: Sensitivity,
    accepts_restricted: bool,
) -> str:
    """Keep one blob of pushed content, checked against its digest, size and label.

    Content is sent before the revisions whose cases hold it, labelled as
    the most sensitive of them.

    Raises:
        RestrictedReceiveRefusedError: The content is restricted, and the
            remote does not accept restricted data.
        ReceiveRefusedError: The content is larger than a remote accepts,
            or its bytes are not its digest.
    """

    if sensitivity is Sensitivity.RESTRICTED and not accepts_restricted:
        raise RestrictedReceiveRefusedError(restricted_refusal(f"Content {digest} is restricted"))

    if len(data) > MAX_CONTENT_BYTES:
        raise ReceiveRefusedError(
            f"Content {digest} is {len(data)} bytes; a remote accepts content of at most "
            f"{MAX_CONTENT_BYTES} bytes."
        )

    held = content_bytes_digest(data)

    if held != digest:
        raise ReceiveRefusedError(f"Content sent as {digest} is {held}.")

    return store.put(data)


@dataclass(frozen=True)
class _Planned:
    """One revision to save: its record, its document as this Azathoth reads it, and its base."""

    record: RevisionRecord
    document: BaseModel
    forks: bool


def _capitalized(
    lineage: Lineage,
) -> str:
    """Return a lineage's name as a sentence begins with it."""

    text = str(lineage)

    return text[:1].upper() + text[1:]


def _read(
    record: RevisionRecord,
) -> BaseModel:
    """Return a record's document as this Azathoth reads it, checked against its content digest.

    Raises:
        ReceiveRefusedError: This Azathoth cannot read the document, or
            reads it as other content than its digest names.
    """

    model = READERS[record.lineage.kind]

    try:
        document = model.model_validate(record.document)
    except ValidationError as exc:
        raise ReceiveRefusedError(
            f"Revision {record.revision_digest} of {record.lineage} is not a "
            f"{record.lineage.kind.value} document Azathoth {__version__} reads: "
            f"{exc.errors()[0]['msg']}."
        ) from None

    read = content_digest(document)

    if read != record.content_digest:
        raise ReceiveRefusedError(
            f"Azathoth {__version__} reads revision {record.revision_digest} of "
            f"{record.lineage} as content {read}, not {record.content_digest}; send it from "
            "an Azathoth that reads it as its digest names."
        )

    return document


def _plan_lineage(
    lineage: Lineage,
    records: Sequence[RevisionRecord],
    held: tuple[LineageRecord, ...],
    *,
    fork: bool,
) -> tuple[list[_Planned], int]:
    """Return the revisions of one lineage to save, and how many were already held.

    Raises:
        DivergedError: The first new revision does not build on the latest
            held one, and the bundle is not one to fork on.
        ReceiveRefusedError: It builds on a revision not held, or begins
            a history where another is held.
    """

    digests = {record.revision_digest for record in held}
    new = [record for record in records if record.revision_digest not in digests]
    skipped = len(records) - len(new)

    if not new:
        return [], skipped

    first = new[0]
    latest = max(held, key=lambda record: record.number, default=None)

    if first.parent_digest is not None and first.parent_digest not in digests:
        raise ReceiveRefusedError(
            f"Revision {first.revision_digest} of {lineage} builds on {first.parent_digest}, "
            "which is not held here; send the revisions before it too."
        )

    builds_on_latest = (
        latest.revision_digest if latest is not None else None
    ) == first.parent_digest
    forks = not builds_on_latest

    if forks and first.parent_digest is None:
        raise ReceiveRefusedError(
            f"Revision {first.revision_digest} of {lineage} begins its history, but another "
            "history of it is held here."
        )

    if forks and not fork:
        assert latest is not None

        raise DivergedError(
            f"{_capitalized(lineage)} has diverged: its latest revision here, "
            f"{latest.revision_digest}, is not the one revision {first.revision_digest} builds "
            "on. Pull first, then push again."
        )

    return [_Planned(record=record, document=_read(record), forks=forks) for record in new], skipped


def receive(
    bundle: PushBundle,
    *,
    workflows: WorkflowRepository,
    tools: ToolRepository,
    benchmarks: BenchmarkRepository,
    content: ContentStore,
    accepts_restricted: bool,
    fork: bool = False,
) -> ReceiveReport:
    """Save a bundle's revisions that are not held, after checking every one of them.

    `fork` is for a pull: a diverged lineage's revisions are saved on the
    revision they build on, forking it. A push never forks.

    Raises:
        RestrictedReceiveRefusedError: The bundle carries restricted data,
            and the instance does not accept it.
        DivergedError: A lineage has diverged, and `fork` is false.
        ReceiveRefusedError: A revision cannot be read as its digest names,
            builds on one not held, or holds content not held.
    """

    if bundle.sensitivity is Sensitivity.RESTRICTED and not accepts_restricted:
        raise RestrictedReceiveRefusedError(restricted_refusal("This push carries restricted data"))

    by_lineage: dict[Lineage, list[RevisionRecord]] = {}

    for record in bundle.revisions:
        by_lineage.setdefault(record.lineage, []).append(record)

    planned: list[_Planned] = []
    already_held = 0

    for lineage, records in by_lineage.items():
        held = lineage_records(lineage, workflows=workflows, tools=tools, benchmarks=benchmarks)
        lineage_plan, skipped = _plan_lineage(lineage, records, held, fork=fork)
        planned.extend(lineage_plan)
        already_held += skipped

    for step in planned:
        if isinstance(step.document, BenchmarkDataset):
            for case in step.document.cases:
                for ref in content_refs(case.input):
                    if not content.contains(ref.digest):
                        raise ReceiveRefusedError(
                            f"Content {ref.digest}, which revision "
                            f"{step.record.revision_digest} of {step.record.lineage} holds, is "
                            "not held here; send it first."
                        )

    received = tuple(
        _save(step, workflows=workflows, tools=tools, benchmarks=benchmarks) for step in planned
    )
    forked: list[Lineage] = []

    for step in planned:
        if step.forks and step.record.lineage not in forked:
            forked.append(step.record.lineage)

    return ReceiveReport(received=received, already_held=already_held, forked=tuple(forked))


def _save(
    step: _Planned,
    *,
    workflows: WorkflowRepository,
    tools: ToolRepository,
    benchmarks: BenchmarkRepository,
) -> ReceivedRevision:
    """Save one checked revision on its parent, and return it as numbered here.

    Raises:
        ReceiveRefusedError: The repository refused it, as a tool document
            whose artifact IDs belong to another tool, or saving it made a
            revision of another digest.
    """

    record = step.record
    document = step.document
    based_on = record.parent_digest

    try:
        if isinstance(document, WorkflowSpecification):
            workflows.save(document, author=record.author, based_on=based_on)
        elif isinstance(document, ToolDocument):
            tools.save_document(document, author=record.author, based_on=based_on)
        elif isinstance(document, BenchmarkDataset):
            benchmarks.save(document, author=record.author, based_on=based_on)
    except ValueError as exc:
        raise ReceiveRefusedError(
            f"Revision {record.revision_digest} of {record.lineage} cannot be saved here: {exc}"
        ) from exc

    saved = next(
        (
            held
            for held in lineage_records(
                record.lineage,
                workflows=workflows,
                tools=tools,
                benchmarks=benchmarks,
            )
            if held.revision_digest == record.revision_digest
        ),
        None,
    )

    if saved is None:
        raise ReceiveRefusedError(
            f"Revision {record.revision_digest} of {record.lineage} was saved as another revision."
        )

    return ReceivedRevision(
        lineage=record.lineage,
        revision_digest=record.revision_digest,
        number=saved.number,
    )


__all__ = [
    "ACCEPT_RESTRICTED_HINT",
    "READERS",
    "DivergedError",
    "ReceiveRefusedError",
    "ReceiveReport",
    "ReceivedRevision",
    "RestrictedReceiveRefusedError",
    "receive",
    "receive_content",
    "restricted_refusal",
]

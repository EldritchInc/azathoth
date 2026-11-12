"""The records a push carries, each checked against its digests (ADR 0124).

A revision travels as its document's JSON, beside the digests that name it.
Each record is checked without the model that made the document: the JSON
digest of the document is its content digest, and the revision digest is
computed again from the lineage, the content digest and the parent. A record
that disagrees with its digests is refused before anything reads it.
"""

from collections.abc import Container
from typing import Annotated, Final
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from azathoth.inputs import ContentRef
from azathoth.remote.protocol import PROTOCOL_VERSION
from azathoth.revisions import (
    CONTENT_DIGEST_PATTERN,
    Author,
    Lineage,
    RevisionKind,
    json_digest,
    revision_digest,
)
from azathoth.sensitivity import (
    DEFAULT_SENSITIVITY,
    UNKNOWN_DATA_POLICY,
    DataPolicy,
    Sensitivity,
    most_sensitive,
)
from azathoth.tools import ENVIRONMENT_GRANT_PATTERN

Digest = Annotated[str, Field(pattern=CONTENT_DIGEST_PATTERN)]
"""A lowercase sha256 hex digest."""

LABELS: Final = frozenset(label.value for label in Sensitivity)
"""Every sensitivity label, as data names it."""


def _member(
    value: JsonValue,
    key: str,
) -> JsonValue:
    """Return one key of a JSON object, or None when the value is no object or lacks it."""

    if not isinstance(value, dict):
        return None

    return value.get(key)


def _document_identity(
    kind: RevisionKind,
    document: JsonValue,
) -> tuple[JsonValue, JsonValue]:
    """Return the ID and tool version a document names, as JSON, for its kind."""

    if kind is RevisionKind.WORKFLOW:
        return _member(_member(document, "metadata"), "id"), None

    if kind is RevisionKind.TOOL:
        definition = _member(document, "definition")

        return _member(definition, "id"), _member(definition, "version")

    return _member(document, "id"), None


def _names_lineage(
    lineage: Lineage,
    document: JsonValue,
) -> bool:
    """Return whether a document is one of a lineage's, by the ID and version it names."""

    identifier, version = _document_identity(lineage.kind, document)

    if not isinstance(identifier, str):
        return False

    try:
        named = UUID(identifier)
    except ValueError:
        return False

    return named == lineage.id and version == lineage.version


class RevisionRecord(BaseModel):
    """One revision as a push carries it: its document's JSON, and the digests that name it.

    `document` is the JSON dump of a workflow specification, a tool document
    or a benchmark dataset, as its lineage's kind says. The remote numbers a
    revision it receives itself; its revision digest is its identity.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    lineage: Lineage

    revision_digest: Digest

    parent_digest: Digest | None

    content_digest: Digest

    author: Author | None = None

    document: JsonValue

    @model_validator(mode="after")
    def require_its_digests(
        self,
    ) -> "RevisionRecord":
        """Refuse a record whose document or identity disagrees with its digests.

        Raises:
            ValueError: The document is not one of the lineage's, its JSON
                digest is not the content digest, the revision digest is not
                the digest of the lineage, content and parent, or a
                benchmark case names an unknown label.
        """

        if not _names_lineage(self.lineage, self.document):
            raise ValueError(
                f"Revision {self.revision_digest} holds a document that is not one of "
                f"{self.lineage}'s."
            )

        held = json_digest(self.document)

        if held != self.content_digest:
            raise ValueError(
                f"Revision {self.revision_digest} of {self.lineage} holds content {held}, "
                f"not its content digest {self.content_digest}."
            )

        computed = revision_digest(
            self.lineage,
            content_digest=self.content_digest,
            parent_digest=self.parent_digest,
        )

        if computed != self.revision_digest:
            raise ValueError(
                f"Revision {self.revision_digest} of {self.lineage} is not the digest of its "
                f"lineage, content and parent, which is {computed}."
            )

        document_sensitivity(self.lineage, self.document)

        return self

    @property
    def sensitivity(
        self,
    ) -> Sensitivity:
        """Return the label of the revision's data: a benchmark's most sensitive case's."""

        return document_sensitivity(self.lineage, self.document)


def document_sensitivity(
    lineage: Lineage,
    document: JsonValue,
) -> Sensitivity:
    """Return the label of a document's data: a benchmark's is its most sensitive case's.

    A workflow or tool document holds no run's data, so it is internal, as is
    a benchmark whose cases name no label (ADR 0123).

    Raises:
        ValueError: A benchmark case names a label that is not one.
    """

    if lineage.kind is not RevisionKind.BENCHMARK:
        return DEFAULT_SENSITIVITY

    cases = _member(document, "cases")
    labels: list[Sensitivity | None] = []

    for case in cases if isinstance(cases, list) else ():
        label = _member(case, "sensitivity")

        if label is None:
            labels.append(None)
            continue

        if not isinstance(label, str) or label not in LABELS:
            raise ValueError(
                f"A case of {lineage} is labelled {label!r}, which is not a sensitivity label."
            )

        labels.append(Sensitivity(label))

    return most_sensitive(labels)


class ContentRecord(BaseModel):
    """Binary content a pushed benchmark's cases hold, and the label of the data it is.

    Content carries no label of its own in the content store (ADR 0123); a
    record's label is the most sensitive of the cases that hold it, so the
    remote, and a pull, treat it as those cases are treated.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    content: ContentRef

    sensitivity: Sensitivity = DEFAULT_SENSITIVITY

    @property
    def digest(
        self,
    ) -> str:
        """Return the content's digest."""

        return self.content.digest


class PushBundle(BaseModel):
    """What one push sends: revisions, parents before children, and the content they hold.

    Within a lineage each revision's parent is the revision before it in the
    bundle. A lineage's first revision in the bundle names a parent the
    remote already holds, or none.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    protocol: int = Field(
        default=PROTOCOL_VERSION,
        ge=1,
    )

    revisions: tuple[RevisionRecord, ...] = ()

    content: tuple[ContentRecord, ...] = ()

    @model_validator(mode="after")
    def require_parents_before_children(
        self,
    ) -> "PushBundle":
        """Refuse a bundle that repeats a revision or content, or orders a lineage out of line.

        Raises:
            ValueError: A revision or content digest appears twice, or a
                revision's parent is not the revision before it in its
                lineage.
        """

        seen: set[str] = set()
        last: dict[Lineage, str] = {}

        for record in self.revisions:
            if record.revision_digest in seen:
                raise ValueError(f"Revision {record.revision_digest} appears twice in the push.")

            seen.add(record.revision_digest)
            before = last.get(record.lineage)

            if before is not None and record.parent_digest != before:
                raise ValueError(
                    f"Revision {record.revision_digest} of {record.lineage} does not build on "
                    f"the revision before it in the push, {before}."
                )

            last[record.lineage] = record.revision_digest

        digests = [record.digest for record in self.content]

        for digest in digests:
            if digests.count(digest) > 1:
                raise ValueError(f"Content {digest} appears twice in the push.")

        return self

    @property
    def sensitivity(
        self,
    ) -> Sensitivity:
        """Return the most sensitive label of anything the bundle carries."""

        return most_sensitive(
            (
                *(record.sensitivity for record in self.revisions),
                *(record.sensitivity for record in self.content),
            )
        )


class MissingResponse(BaseModel):
    """Which of the offered revisions and content the remote does not hold, as offered."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    revisions: tuple[Digest, ...] = ()

    content: tuple[Digest, ...] = ()


class MissingRequest(BaseModel):
    """The revision and content digests a client offers, before it sends anything.

    The remote answers with those it does not hold, so a push carries only
    what is missing. It looks for the revisions only in `lineages`, those
    the push would send.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    lineages: tuple[Lineage, ...] = ()

    revisions: tuple[Digest, ...] = ()

    content: tuple[Digest, ...] = ()

    def missing(
        self,
        *,
        held_revisions: Container[str],
        held_content: Container[str],
    ) -> MissingResponse:
        """Return the offered digests not held, in the order offered."""

        return MissingResponse(
            revisions=tuple(digest for digest in self.revisions if digest not in held_revisions),
            content=tuple(digest for digest in self.content if digest not in held_content),
        )


class PullRequest(BaseModel):
    """The documents a client asks a remote for, and the revisions it already holds.

    A remote leaves out the revisions named in `held`. A restricted
    benchmark comes only with `include_restricted` (ADR 0123).
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    protocol: int = Field(
        default=PROTOCOL_VERSION,
        ge=1,
    )

    roots: tuple[Lineage, ...] = Field(
        min_length=1,
    )

    held: tuple[Digest, ...] = ()

    include_restricted: bool = False


class PullResponse(BaseModel):
    """What a remote sends for a pull: a bundle, and what it withheld or could not gather.

    `withheld` names the restricted benchmarks left out of a pull that did
    not ask for restricted data; `unresolved` is the closure's.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    bundle: PushBundle

    withheld: tuple[Lineage, ...] = ()

    unresolved: tuple[str, ...] = ()


class Head(BaseModel):
    """One lineage as an instance holds it: its latest revision's chain, and what is in production.

    `chain` is the latest revision's digest and the digests it was reached
    by, oldest first; `number` is the latest revision's number there. A
    workflow's `production_digest` is the revision in production there, or
    None where it is not in production.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    lineage: Lineage

    chain: tuple[Digest, ...] = Field(
        min_length=1,
    )

    number: int = Field(
        ge=1,
    )

    production_digest: Digest | None = None


class HeadsRequest(BaseModel):
    """The lineages a client asks a remote about; none asks about every one it holds."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    protocol: int = Field(
        default=PROTOCOL_VERSION,
        ge=1,
    )

    lineages: tuple[Lineage, ...] = ()


class HeadsResponse(BaseModel):
    """The head of each lineage asked about that the remote holds; one it does not is left out."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    heads: tuple[Head, ...] = ()


class PortfolioRecord(BaseModel):
    """One model a remote's portfolio authorizes, and the data policy declared for it."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    identifier: str = Field(
        min_length=1,
    )

    data_policy: DataPolicy = UNKNOWN_DATA_POLICY


class PortfolioResponse(BaseModel):
    """The models a remote's portfolio authorizes, in its order."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    entries: tuple[PortfolioRecord, ...] = ()


CredentialName = Annotated[str, Field(pattern=ENVIRONMENT_GRANT_PATTERN)]
"""An environment variable's name, or a grant ending in `*` covering every one it begins."""


class CredentialsRequest(BaseModel):
    """The environment variables a push's tools need, by name; no value ever travels."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    names: tuple[CredentialName, ...] = ()


class CredentialsResponse(BaseModel):
    """Which of the names asked about the remote's environment does not set, in the order asked."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    missing: tuple[CredentialName, ...] = ()


__all__ = [
    "ContentRecord",
    "CredentialsRequest",
    "CredentialsResponse",
    "Head",
    "HeadsRequest",
    "HeadsResponse",
    "MissingRequest",
    "MissingResponse",
    "PortfolioRecord",
    "PortfolioResponse",
    "PullRequest",
    "PullResponse",
    "PushBundle",
    "RevisionRecord",
    "document_sensitivity",
]

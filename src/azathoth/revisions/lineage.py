"""The lineages revisions belong to, and the digests that chain them (ADR 0122)."""

import hashlib
import json
import re
from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.revisions.digest import CONTENT_DIGEST_PATTERN

REVISION_DIGEST_FORMAT: Final = 1
"""The version of the canonical identity a revision digest is computed over."""


class RevisionKind(StrEnum):
    """The kinds of durable document that are imported as revisions."""

    WORKFLOW = "workflow"
    TOOL = "tool"
    BENCHMARK = "benchmark"


class Lineage(BaseModel):
    """The stable identity every revision of one document is appended under.

    A workflow's lineage is its workflow ID and a benchmark's is its dataset
    ID. A tool's is its tool ID and exact version, since each version of a
    tool keeps its own revisions.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    kind: RevisionKind

    id: UUID

    version: str | None = Field(
        default=None,
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_version(
        self,
    ) -> "Lineage":
        """Require a version for a tool lineage, and refuse one for any other."""

        if self.kind is RevisionKind.TOOL and self.version is None:
            raise ValueError("A tool lineage names its tool version.")

        if self.kind is not RevisionKind.TOOL and self.version is not None:
            raise ValueError(f"A {self.kind.value} lineage has no version.")

        return self

    def __str__(
        self,
    ) -> str:
        """Return the lineage as messages name it, such as `tool <id>@<version>`."""

        if self.version is None:
            return f"{self.kind.value} {self.id}"

        return f"{self.kind.value} {self.id}@{self.version}"


def _checked_digest(
    label: str,
    digest: str,
) -> str:
    """Return a digest unchanged, or refuse it when it is not lowercase sha256 hex."""

    if re.fullmatch(CONTENT_DIGEST_PATTERN, digest) is None:
        raise ValueError(f"{label} {digest!r} is not a lowercase sha256 hex digest.")

    return digest


def revision_digest(
    lineage: Lineage,
    *,
    content_digest: str,
    parent_digest: str | None,
) -> str:
    """Return the sha256 hex digest that identifies one revision wherever it is kept.

    It is computed over the revision's canonical identity: the format, the
    lineage's kind, ID and version, the content digest, and the parent
    revision's digest, or null for a lineage's first revision. The identity
    is JSON with sorted keys and no insignificant whitespace, encoded as
    UTF-8.

    Because each digest covers its parent's, it covers the revision's whole
    history: two instances that hold a revision with the same digest hold
    the same content reached by the same revisions. Who imported it and
    when are not part of it, so the same work recorded by two people is one
    revision.

    Raises:
        ValueError: A digest given is not lowercase sha256 hex.
    """

    identity = {
        "format": REVISION_DIGEST_FORMAT,
        "kind": lineage.kind.value,
        "id": str(lineage.id),
        "version": lineage.version,
        "content": _checked_digest("Content digest", content_digest),
        "parent": (
            None if parent_digest is None else _checked_digest("Parent digest", parent_digest)
        ),
    }

    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    return hashlib.sha256(
        canonical.encode("utf-8"),
    ).hexdigest()


__all__ = [
    "REVISION_DIGEST_FORMAT",
    "Lineage",
    "RevisionKind",
    "revision_digest",
]

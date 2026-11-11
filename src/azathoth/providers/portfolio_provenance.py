"""Who added each portfolio entry, and who declared its data policy, and when (ADR 0122, 0123)."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from azathoth.revisions import CONTENT_DIGEST_PATTERN, Author


class PortfolioProvenance(BaseModel):
    """Who added one portfolio entry, when, and the digest of what they added (ADR 0122).

    Entries added before provenance was recorded have no author and no time.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    identifier: str = Field(
        min_length=1,
    )

    content_digest: str = Field(
        pattern=CONTENT_DIGEST_PATTERN,
    )

    author: Author | None = None

    added_at: datetime | None = None


class PolicyDeclaration(BaseModel):
    """Who declared one portfolio entry's current data policy, and when (ADR 0123).

    It is recorded beside the entry, never in it, so who declares a policy
    is no part of the entry's digest.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    identifier: str = Field(
        min_length=1,
    )

    author: Author | None = None

    declared_at: datetime


__all__ = [
    "PolicyDeclaration",
    "PortfolioProvenance",
]

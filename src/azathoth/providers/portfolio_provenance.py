"""Who added each portfolio entry, and when (ADR 0122)."""

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


__all__ = [
    "PortfolioProvenance",
]

"""The durable rotation of language models that judge semantic outcomes."""

import hashlib
import json

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.evaluation.models import ExpectedOutcome


class JudgeEntry(BaseModel):
    """Name one provider model that may judge semantic outcomes."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)

    model: str = Field(min_length=1)

    @property
    def identifier(
        self,
    ) -> str:
        """Return the provider-qualified model identifier."""

        return f"{self.provider}/{self.model}"


class JudgeRotation(BaseModel):
    """Describe the ordered judges that semantic outcomes are assigned to.

    A rotation of one judge is valid. Each expectation is assigned a first
    judge by a stable hash of the expectation, so every candidate judged
    against the same benchmark case meets the same judge first, and the
    remaining judges follow in rotation order as fallbacks.
    """

    model_config = ConfigDict(frozen=True)

    entries: tuple[
        JudgeEntry,
        ...,
    ] = ()

    @model_validator(mode="after")
    def reject_duplicate_identifiers(
        self,
    ) -> "JudgeRotation":
        """Reject a judge that appears in the rotation more than once."""

        identifiers = self.identifiers

        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Judge rotation cannot contain duplicate model identifiers.")

        return self

    @property
    def identifiers(
        self,
    ) -> tuple[
        str,
        ...,
    ]:
        """Return judge identifiers in rotation order."""

        return tuple(entry.identifier for entry in self.entries)

    def get(
        self,
        identifier: str,
    ) -> JudgeEntry | None:
        """Return one judge by provider-qualified identifier."""

        return next(
            (entry for entry in self.entries if entry.identifier == identifier),
            None,
        )

    def judges_for(
        self,
        expected: ExpectedOutcome,
    ) -> tuple[
        JudgeEntry,
        ...,
    ]:
        """Return every judge in the order they should try one expectation.

        The first judge is chosen by a stable hash of the expectation; the
        rest follow in rotation order, wrapping around, so each judge appears
        exactly once.

        Raises:
            ValueError: The rotation contains no judges.
        """

        if not self.entries:
            raise ValueError("Judge rotation is empty.")

        start = expectation_hash(expected) % len(self.entries)

        return self.entries[start:] + self.entries[:start]


def expectation_hash(
    expected: ExpectedOutcome,
) -> int:
    """Return a stable integer hash of one expectation.

    The hash covers the description, value, and comparison in canonical JSON,
    so it is identical across processes, platforms, and dictionary key order.
    """

    canonical = json.dumps(
        expected.model_dump(
            mode="json",
        ),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    digest = hashlib.sha256(
        canonical.encode("utf-8"),
    ).digest()

    return int.from_bytes(
        digest[:8],
        "big",
    )

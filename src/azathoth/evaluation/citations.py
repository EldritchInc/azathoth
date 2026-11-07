"""Comparing results that cite, by what they cite (ADR 0117).

A cited step's result holds its citations, each replaced by its check: the
source, segment and quote as cited, then the status, the anchor, and, for a
provider's own citation, the pages and the text it supports (ADR 0116). A
check's anchor names digests and offsets, so two results citing the same
segment with quotes worded a little differently, or verified a little
differently, would never be equal.

Before an exact, normalized or semantic comparison, every citation and every
check in either value compares as the segment it cites, `{source, segment}`,
so a case judges the answer and what it cited, and its citation expectation
judges whether the citations verified.
"""

from typing import Final

from pydantic import JsonValue

CITED_KEYS: Final = frozenset({"source", "segment", "quote"})
"""The keys every citation and every check holds."""

CHECK_KEYS: Final = CITED_KEYS | frozenset({"status", "anchor", "supports", "pages"})
"""The keys a check may hold besides a citation's."""


def is_cited(
    value: JsonValue,
) -> bool:
    """Return whether one value is a citation or a check of one.

    It is an object holding at least a citation's keys and no key a check
    does not have, whose source and quote are strings and whose segment is a
    string, or null for a provider's citation no segment verified.
    """

    if not isinstance(value, dict) or not CITED_KEYS <= set(value) <= CHECK_KEYS:
        return False

    segment = value["segment"]

    return (
        isinstance(value["source"], str)
        and isinstance(value["quote"], str)
        and (segment is None or isinstance(segment, str))
    )


def compared_value(
    value: JsonValue,
) -> JsonValue:
    """Return one value with every citation and check in it as the segment it cites."""

    if is_cited(value):
        assert isinstance(value, dict)

        return {"source": value["source"], "segment": value["segment"]}

    if isinstance(value, dict):
        return {key: compared_value(item) for key, item in value.items()}

    if isinstance(value, list):
        return [compared_value(item) for item in value]

    return value


__all__ = [
    "CHECK_KEYS",
    "CITED_KEYS",
    "compared_value",
    "is_cited",
]

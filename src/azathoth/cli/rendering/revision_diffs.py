"""Rendering a comparison of two revisions, as the `diff` commands print it (ADR 0133)."""

import json
from typing import Final

from pydantic import JsonValue

from azathoth.api import RevisionChange, RevisionComparison

WITHHELD: Final = "(withheld)"
"""What a value withheld from a comparison prints as."""

_MARKS: Final = {"added": "+", "removed": "-", "changed": "~"}


def _value(
    value: JsonValue,
    *,
    withheld: bool,
) -> str:
    """Return one side of a change: a scalar as JSON, an object or a list abbreviated."""

    if value is None and withheld:
        return WITHHELD

    if isinstance(value, dict) and value:
        return "{...}"

    if isinstance(value, list) and value:
        return "[...]"

    return json.dumps(value, ensure_ascii=False)


def render_revision_change(
    change: RevisionChange,
) -> str:
    """Return one change as a line: `~ <pointer>: <before> -> <after>`, `+` or `-`."""

    if change.kind == "added":
        shown = _value(change.after, withheld=change.withheld)
    elif change.kind == "removed":
        shown = _value(change.before, withheld=change.withheld)
    else:
        before = _value(change.before, withheld=change.withheld)
        shown = f"{before} -> {_value(change.after, withheld=change.withheld)}"

    return f"{_MARKS[change.kind]} {change.pointer}: {shown}"


def render_revision_comparison(
    comparison: RevisionComparison,
) -> str:
    """Return a comparison as a line per change, or a line saying the revisions are identical."""

    before = comparison.before.number
    after = comparison.after.number

    if comparison.identical:
        return f"Revisions {before} and {after} are identical."

    return "\n".join(render_revision_change(change) for change in comparison.changes)


__all__ = [
    "WITHHELD",
    "render_revision_change",
    "render_revision_comparison",
]

"""Comparing two revisions' documents value by value (ADR 0133).

A comparison never guesses at moves: objects are compared key by key and
lists item by item, so what it reports is exactly what differs where.
"""

import copy
from collections.abc import Iterator, Sequence
from typing import Final

from pydantic import JsonValue

from azathoth.api.models import Revision, RevisionChange, RevisionComparison
from azathoth.evaluation import BenchmarkDataset
from azathoth.sensitivity import Sensitivity

Location = tuple[str | int, ...]
"""Where in a document a value is: the keys and indexes leading to it."""

RESTRICTED_CASE_VALUES: Final[tuple[Location, ...]] = (
    ("input",),
    ("input_provenance",),
    ("expected", "value"),
    ("expected", "citations"),
)
"""The values of a case that only a caller who may read restricted data sees (ADR 0130)."""


def json_pointer(
    location: Location,
) -> str:
    """Return a location as an RFC 6901 JSON Pointer, escaping `~` and `/`."""

    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in location)


def _same(
    before: JsonValue,
    after: JsonValue,
) -> bool:
    """Return whether two leaf values are the same JSON: `1`, `1.0` and `true` all differ."""

    return type(before) is type(after) and before == after


def _differences(
    before: JsonValue,
    after: JsonValue,
    location: Location,
) -> Iterator[tuple[str, Location, JsonValue, JsonValue]]:
    """Yield each difference under one location, in document order."""

    if isinstance(before, dict) and isinstance(after, dict):
        for key, value in before.items():
            if key in after:
                yield from _differences(value, after[key], (*location, key))
            else:
                yield "removed", (*location, key), value, None

        for key, value in after.items():
            if key not in before:
                yield "added", (*location, key), None, value

        return

    if isinstance(before, list) and isinstance(after, list):
        for index, (old, new) in enumerate(zip(before, after, strict=False)):
            yield from _differences(old, new, (*location, index))

        for index in range(len(after), len(before)):
            yield "removed", (*location, index), before[index], None

        for index in range(len(before), len(after)):
            yield "added", (*location, index), None, after[index]

        return

    if not _same(before, after):
        yield "changed", location, before, after


def _withheld(
    value: JsonValue,
    location: Location,
    withheld: Sequence[Location],
) -> tuple[JsonValue, bool]:
    """Return a value with what is withheld at or under its location left out as `None`.

    The second value says whether anything was left out.
    """

    if any(location[: len(hidden)] == hidden for hidden in withheld):
        return None, value is not None

    inner = [hidden[len(location) :] for hidden in withheld if hidden[: len(location)] == location]

    if not inner:
        return value, False

    kept = copy.deepcopy(value)
    left_out = False

    for path in inner:
        parent: JsonValue = kept

        for part in path[:-1]:
            parent = _child(parent, part)

        left_out = _left_out(parent, path[-1]) or left_out

    return kept, left_out


def _left_out(
    parent: JsonValue,
    part: str | int,
) -> bool:
    """Replace the value one key or index below `parent` with `None`, saying whether it held one."""

    if isinstance(parent, dict) and isinstance(part, str):
        held = parent.get(part) is not None

        if held:
            parent[part] = None

        return held

    if isinstance(parent, list) and isinstance(part, int) and part < len(parent):
        held = parent[part] is not None
        parent[part] = None

        return held

    return False


def _child(
    value: JsonValue,
    part: str | int,
) -> JsonValue:
    """Return the value one key or index below another, or `None` where there is none."""

    if isinstance(value, dict) and isinstance(part, str):
        return value.get(part)

    if isinstance(value, list) and isinstance(part, int) and part < len(value):
        return value[part]

    return None


def compare_documents(
    before: Revision,
    after: Revision,
    documents: tuple[JsonValue, JsonValue],
    *,
    withheld: tuple[Sequence[Location], Sequence[Location]] = ((), ()),
) -> RevisionComparison:
    """Return what differs between two revisions' documents.

    `withheld` names, for the document before and the one after, the values
    each change leaves out as `None`, wherever the change holds them.
    """

    changes: list[RevisionChange] = []

    for kind, location, old, new in _differences(documents[0], documents[1], ()):
        shown_before, hid_before = _withheld(old, location, withheld[0])
        shown_after, hid_after = _withheld(new, location, withheld[1])

        changes.append(
            RevisionChange.model_validate(
                {
                    "kind": kind,
                    "pointer": json_pointer(location),
                    "before": shown_before,
                    "after": shown_after,
                    "withheld": hid_before or hid_after,
                }
            )
        )

    return RevisionComparison(
        before=before,
        after=after,
        identical=before.content_digest == after.content_digest,
        changes=tuple(changes),
    )


def restricted_case_values(
    dataset: BenchmarkDataset,
) -> tuple[Location, ...]:
    """Return where a dataset's document holds its restricted cases' values."""

    return tuple(
        ("cases", index, *value)
        for index, case in enumerate(dataset.cases)
        if case.sensitivity is Sensitivity.RESTRICTED
        for value in RESTRICTED_CASE_VALUES
    )


__all__ = [
    "RESTRICTED_CASE_VALUES",
    "Location",
    "compare_documents",
    "json_pointer",
    "restricted_case_values",
]

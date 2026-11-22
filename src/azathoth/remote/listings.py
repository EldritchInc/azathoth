"""What a listing leaves out for a caller the policy does not let see each thing (ADR 0127).

A call that lists, `workflows.list` or `runs.list`, asks its policy for
its actions once, for the listing, and then again for each thing it
returns, named as the policy is asked about any resource: its kind and its
ID. A thing the policy refuses is left out, and the listing still answers,
so a policy may decide by resource without a caller learning what it
cannot see.

`LISTED_IDS` names, for each kind of thing the catalog says a call lists,
the field of each item that holds its ID, and a test holds every kind the
catalog names to one.

This module needs no web framework.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Final

from azathoth.api.calls import ServiceCall
from azathoth.remote.seams import Policy, Principal

LISTED_IDS: Final[Mapping[str, str]] = {
    "workflow": "id",
    "tool": "id",
    "benchmark": "id",
    "goal": "id",
    "execution": "execution_id",
    "run": "run_id",
    "invocation": "invocation_id",
    "experiment": "experiment_id",
}
"""The field holding each listed item's ID, by the kind of thing it is."""


def listed_resource(
    kind: str,
    item: Any,
) -> str:
    """Return one listed item as the policy is asked about it: its kind and its ID.

    Raises:
        KeyError: The catalog names no listing of that kind.
    """

    return f"{kind} {getattr(item, LISTED_IDS[kind])}"


def visible(
    call: ServiceCall,
    items: Sequence[Any],
    policy: Policy,
    principal: Principal,
) -> tuple[Any, ...]:
    """Return the items of a listing the policy lets a principal see, in the order listed.

    An item is kept when the policy allows every action of the call on it.
    A call that lists nothing returns its items as they are.
    """

    kind = call.lists

    if kind is None:
        return tuple(items)

    return tuple(
        item
        for item in items
        if all(
            policy.decide(principal, action, listed_resource(kind, item)).allowed
            for action in call.actions
        )
    )


__all__ = [
    "LISTED_IDS",
    "listed_resource",
    "visible",
]

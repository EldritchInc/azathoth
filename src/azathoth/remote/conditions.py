"""When a call asks its policy for more than its own actions (ADRs 0127 and 0134).

`azathoth.api.calls` names, for each call, the actions it asks only when
something holds: a process tool asks `import_process_tool` as well as
`import_tool`, and a restricted benchmark `read_restricted` as well as
`read_catalog`. Each such condition is checked here, once, by a
`ConditionCheck`, and a test holds every condition the catalog names to
exactly one check.

A check is told either from the call's arguments, before it runs, or from
its result, before that is sent. What changes something is always told
before, so nothing is changed for a caller the policy would refuse. What
only reads is told from what it read where that is the only way to know,
and a refusal then sends nothing of it. A check told before may read
through the caller's own instance, as reading the run a case is made from
does.

This module needs no web framework.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from azathoth.api.calls import SERVICE_CALLS, Condition
from azathoth.api.instance import Azathoth
from azathoth.sensitivity import Sensitivity
from azathoth.tools import PROCESS_TOOL_RUNTIME, ToolDocumentError, decode_tool_document

Arguments = Mapping[str, Any]
"""A call's arguments, by name, as the remote read them."""

Before = Callable[[Azathoth, Arguments], bool]
"""Whether a condition holds, told from a call's arguments before it runs."""

After = Callable[[Arguments, Any], bool]
"""Whether a condition holds, told from what a call returned before it is sent."""


@dataclass(frozen=True)
class ConditionCheck:
    """How a remote tells whether one call's condition holds: before it runs, or after."""

    call: str
    condition: Condition
    before: Before | None = None
    after: After | None = None


def _restricted(
    value: Any,
) -> bool:
    """Return whether a result is labelled restricted."""

    return getattr(value, "sensitivity", None) is Sensitivity.RESTRICTED


def _process_tool(
    instance: Azathoth,
    arguments: Arguments,
) -> bool:
    """Return whether a tool document to import has a process implementation.

    A document that is not a tool document is none: the call itself refuses it.
    """

    document = arguments["document"]
    text = document if isinstance(document, str) else json.dumps(dict(document))

    try:
        decoded = decode_tool_document(text)
    except ToolDocumentError:
        return False

    return any(
        implementation.runtime == PROCESS_TOOL_RUNTIME for implementation in decoded.implementations
    )


def _from_a_run(
    instance: Azathoth,
    arguments: Arguments,
) -> bool:
    """Return whether a case is made from a run."""

    return arguments.get("run_id") is not None


def _from_a_restricted_run(
    instance: Azathoth,
    arguments: Arguments,
) -> bool:
    """Return whether a case is made from a run of restricted input, reading the run.

    It is checked after reading runs is allowed, since it reads one.
    """

    run_id = arguments.get("run_id")

    return run_id is not None and _restricted(instance.runs.get(run_id))


def _compares_a_restricted_case(
    instance: Azathoth,
    arguments: Arguments,
) -> bool:
    """Return whether a comparison asked to tell restricted values would tell any.

    The comparison is made first without them: a change it withholds is a
    restricted case's.
    """

    if not arguments.get("include_restricted", True):
        return False

    withheld = instance.benchmarks.compare_revisions(
        arguments["benchmark_id"],
        arguments["before"],
        arguments["after"],
        include_restricted=False,
    )

    return any(change.withheld for change in withheld.changes)


def _from_an_experiment(
    instance: Azathoth,
    arguments: Arguments,
) -> bool:
    """Return whether a workflow is promoted from an experiment's winner."""

    return arguments.get("experiment_id") is not None


def _restricted_result(
    arguments: Arguments,
    result: Any,
) -> bool:
    """Return whether what a call read is labelled restricted."""

    return _restricted(result)


def _also(
    call: str,
    when: str,
) -> Condition:
    """Return the condition of a call that holds when the catalog says it does."""

    (condition,) = [
        condition
        for each in SERVICE_CALLS
        if each.name == call
        for condition in each.also
        if condition.when == when
    ]

    return condition


CONDITION_CHECKS: Final[tuple[ConditionCheck, ...]] = (
    ConditionCheck(
        "tools.import_document",
        _also("tools.import_document", "for a process tool"),
        before=_process_tool,
    ),
    ConditionCheck(
        "benchmarks.get",
        _also("benchmarks.get", "for a restricted benchmark"),
        after=_restricted_result,
    ),
    ConditionCheck(
        "benchmarks.export",
        _also("benchmarks.export", "for a restricted benchmark"),
        after=_restricted_result,
    ),
    ConditionCheck(
        "benchmarks.compare_revisions",
        _also("benchmarks.compare_revisions", "for a restricted case"),
        before=_compares_a_restricted_case,
    ),
    ConditionCheck(
        "benchmarks.case",
        _also("benchmarks.case", "for a restricted case"),
        after=_restricted_result,
    ),
    ConditionCheck(
        "benchmarks.add_case",
        _also("benchmarks.add_case", "when the case is made from a run"),
        before=_from_a_run,
    ),
    ConditionCheck(
        "benchmarks.add_case",
        _also("benchmarks.add_case", "when the case is made from a run of restricted input"),
        before=_from_a_restricted_run,
    ),
    ConditionCheck(
        "runs.get",
        _also("runs.get", "for a run of restricted input"),
        after=_restricted_result,
    ),
    ConditionCheck(
        "invocations.get",
        _also("invocations.get", "for a run of restricted input"),
        after=_restricted_result,
    ),
    ConditionCheck(
        "production.promote",
        _also("production.promote", "when promoted from an experiment"),
        before=_from_an_experiment,
    ),
)
"""How a remote tells, for each call, each condition the catalog names; in the catalog's order."""


def condition_checks(
    call: str,
) -> tuple[ConditionCheck, ...]:
    """Return the checks of one call's conditions, in the order the catalog names them."""

    return tuple(check for check in CONDITION_CHECKS if check.call == call)


__all__ = [
    "CONDITION_CHECKS",
    "After",
    "Arguments",
    "Before",
    "ConditionCheck",
    "condition_checks",
]

"""Whether what a job tells is restricted, so a remote sends it only to who may read it (ADR 0138).

A run is labelled by its input, so a run, a step tried or an invocation a
job starts is restricted when it was submitted with restricted input. A
resumed run or invocation is as its run or invocation is labelled, and a
benchmark run, compared or optimized over as its benchmark is. What a job
names that is no longer there tells nothing, so it is not restricted.
"""

import json
from collections.abc import Callable, Mapping
from typing import Any, Final
from uuid import UUID

from azathoth.api.errors import NotFoundError
from azathoth.api.instance import Azathoth
from azathoth.remote.jobs import ServiceJob
from azathoth.sensitivity import Sensitivity

LABELLED_BY_INPUT: Final = frozenset({"runs.run", "runs.try_step", "runs.invoke"})
"""The jobs whose run is labelled by the input they were submitted with."""


def _labelled(
    value: object,
) -> bool:
    return getattr(value, "sensitivity", None) is Sensitivity.RESTRICTED


def _run(
    instance: Azathoth,
    arguments: Mapping[str, Any],
) -> bool:
    return _labelled(instance.runs.get(UUID(arguments["run_id"])))


def _invocation(
    instance: Azathoth,
    arguments: Mapping[str, Any],
) -> bool:
    return _labelled(instance.invocations.get(UUID(arguments["invocation_id"])))


def _benchmark(
    instance: Azathoth,
    arguments: Mapping[str, Any],
) -> bool:
    return _labelled(instance.benchmarks.get(UUID(arguments["benchmark_id"])))


LABELLED_BY_WHAT_THEY_NAME: Final[Mapping[str, Callable[[Azathoth, Mapping[str, Any]], bool]]] = {
    "runs.resume": _run,
    "invocations.resume": _invocation,
    "benchmarks.run": _benchmark,
    "benchmarks.compare": _benchmark,
    "optimization.optimize": _benchmark,
}
"""The jobs labelled as what they name is, and how each reads it."""


def restricted(
    instance: Azathoth,
    job: ServiceJob,
) -> bool:
    """Return whether what a job tells, its events and its result, is restricted.

    Raises:
        LookupError: The job is of no call that runs as a job.
    """

    arguments: Mapping[str, Any] = json.loads(job.arguments)

    if job.call in LABELLED_BY_INPUT:
        return arguments.get("sensitivity") == Sensitivity.RESTRICTED.value

    labelled = LABELLED_BY_WHAT_THEY_NAME.get(job.call)

    if labelled is None:
        raise LookupError(f"{job.call} does not run as a job.")

    try:
        return labelled(instance, arguments)
    except NotFoundError:
        return False


__all__ = [
    "LABELLED_BY_INPUT",
    "LABELLED_BY_WHAT_THEY_NAME",
    "restricted",
]

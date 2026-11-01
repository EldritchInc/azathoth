"""Live observation of workflow step progress."""

import contextlib
from dataclasses import dataclass
from typing import Protocol

from azathoth.execution import ExecutionResult
from azathoth.workflows.attempt import WorkflowStepAttempt, WorkflowStepFailure
from azathoth.workflows.candidate import WorkflowCandidateStep
from azathoth.workflows.execution import WorkflowStepStatus
from azathoth.workflows.value import WorkflowValue


@dataclass(frozen=True)
class WorkflowStepStarted:
    """A workflow step began its first execution attempt.

    Retries never start a step again, so each executed step starts once.
    Skipped steps and steps whose inputs did not resolve never start.
    """

    step: WorkflowCandidateStep
    layer_index: int


@dataclass(frozen=True)
class WorkflowStepFinished:
    """A workflow step reached its final status.

    An executed step carries its declared values, and its confidence when it
    declares one (ADR 0098). A failed step carries the failure of its final
    attempt. A skipped step carries neither.

    An executed or failed step also carries every attempt it made, and an
    executed step its final execution, so an observer can report what it
    cost and how often it was retried (ADR 0100).
    """

    step: WorkflowCandidateStep
    layer_index: int
    status: WorkflowStepStatus
    values: tuple[WorkflowValue, ...] = ()
    failure: WorkflowStepFailure | None = None
    confidence: float | None = None
    attempts: tuple[WorkflowStepAttempt, ...] = ()
    execution: ExecutionResult | None = None


WorkflowRunEvent = WorkflowStepStarted | WorkflowStepFinished
"""One live notification about workflow step progress."""


class WorkflowRunObserver(Protocol):
    """Receive live workflow step progress as it happens.

    Events arrive in the order steps actually start and finish, so concurrent
    steps of one layer interleave. Observation never changes recorded
    evidence: the runner discards anything an observer raises.
    """

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Receive one workflow run event."""

        ...


class CombinedRunObserver:
    """Deliver every event to several observers, in order.

    One observer that raises never keeps an event from the others.
    """

    def __init__(
        self,
        *observers: WorkflowRunObserver | None,
    ) -> None:
        self._observers = tuple(observer for observer in observers if observer is not None)

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Deliver one event to every observer."""

        for observer in self._observers:
            with contextlib.suppress(Exception):
                observer.observe(event)


def combine_observers(
    *observers: WorkflowRunObserver | None,
) -> WorkflowRunObserver | None:
    """Return one observer delivering to every given one, or None when there are none."""

    present = tuple(observer for observer in observers if observer is not None)

    if not present:
        return None

    if len(present) == 1:
        return present[0]

    return CombinedRunObserver(*present)

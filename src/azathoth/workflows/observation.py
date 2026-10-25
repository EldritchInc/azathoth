"""Live observation of workflow step progress."""

from dataclasses import dataclass
from typing import Protocol

from azathoth.workflows.attempt import WorkflowStepFailure
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

    An executed step carries its declared values. A failed step carries the
    failure of its final attempt. A skipped step carries neither.
    """

    step: WorkflowCandidateStep
    layer_index: int
    status: WorkflowStepStatus
    values: tuple[WorkflowValue, ...] = ()
    failure: WorkflowStepFailure | None = None


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

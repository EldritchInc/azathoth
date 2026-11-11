"""Reading invocations back (ADR 0120).

An invocation is read as `azathoth invocation show` reports it: its input,
who made it, its outcome, and its run, finished or not. Who may read which
invocation is for the caller to decide; the API reads any it is asked for.
"""

from typing import Literal
from uuid import UUID

from pydantic import JsonValue

from azathoth.api.browsing import RepositoriesAccess
from azathoth.api.errors import NotFoundError
from azathoth.api.models import (
    InvocationDetail,
    InvocationError,
    InvocationRun,
    RunStep,
)
from azathoth.api.running import step_status
from azathoth.context import context_sensitivity
from azathoth.workflows import (
    ProductionInvocation,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    WorkflowRun,
    journal_resumes,
)
from azathoth.workflows.production_invocation import PRODUCTION_INVOCATION_EVENT_TYPE


class Invocations:
    """The invocations of an instance's promoted workflows."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
    ) -> None:
        """Read the invocations of the repositories `repositories` returns."""

        self._repositories = repositories

    def get(
        self,
        invocation_id: UUID,
    ) -> InvocationDetail:
        """Return one invocation with its outcome and its run.

        An invocation with no outcome yet is `incomplete`; its run, when its
        journal records one, is named without its steps.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No invocation has this ID.
        """

        repositories = self._repositories()
        invocation = repositories.invocations.get(invocation_id)

        if invocation is None:
            raise NotFoundError(f"No invocation {invocation_id} was found.")

        outcome = repositories.invocations.result(invocation_id)
        association = repositories.invocation_runs.get(invocation_id)
        run_id = (
            association.run_id
            if association is not None
            else repositories.run_journal.invocation_run_id(invocation_id)
        )
        resumes = 0 if run_id is None else journal_resumes(repositories.run_journal.entries(run_id))
        run = repositories.runs.get(association.run_id) if association is not None else None

        status: Literal["succeeded", "failed", "incomplete"] = "incomplete"
        value: JsonValue = None
        error: InvocationError | None = None

        if isinstance(outcome, ProductionInvocationSuccess):
            status = "succeeded"
            value = outcome.result

        if isinstance(outcome, ProductionInvocationFailure):
            status = "failed"
            error = InvocationError(
                code=outcome.error_code.value,
                message=outcome.message,
                metadata=dict(outcome.metadata),
            )

        return InvocationDetail(
            invocation_id=invocation.id,
            workflow_id=invocation.workflow_id,
            created_at=invocation.created_at,
            status=status,
            result=value,
            error=error,
            idempotency_key=invocation.idempotency.key if invocation.idempotency else None,
            input=_input(invocation),
            sensitivity=context_sensitivity(invocation.initial_context),
            caller_metadata=dict(invocation.caller_metadata),
            run=_run(run_id, run, resumes),
            command=f"azathoth invocation show {invocation.id}",
        )


def _input(
    invocation: ProductionInvocation,
) -> JsonValue:
    """Return the input the caller gave one invocation."""

    for event in invocation.initial_context.events:
        if event.event_type == PRODUCTION_INVOCATION_EVENT_TYPE:
            return event.payload.get("input")

    return None


def _run(
    run_id: UUID | None,
    run: WorkflowRun | None,
    resumes: int,
) -> InvocationRun | None:
    """Return an invocation's run, finished or not, if it has one."""

    if run is not None:
        return InvocationRun(
            run_id=run.id,
            finished=True,
            resumes=resumes,
            workflow_revision=run.workflow_revision,
            started_at=run.started_at,
            completed_at=run.completed_at,
            halted=run.halted,
            steps=tuple(
                RunStep(
                    step_id=step.step_id,
                    status=step_status(step.status),
                    attempts=len(step.attempts),
                    confidence=step.confidence,
                )
                for step in run.steps
            ),
        )

    if run_id is not None:
        return InvocationRun(run_id=run_id, finished=False, resumes=resumes)

    return None


__all__ = [
    "Invocations",
]

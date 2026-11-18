"""Reading invocations back, listing them, and resuming them (ADR 0120, ADR 0128).

An invocation is read as `azathoth invocation show` reports it: its input,
who made it, its outcome, and its run, finished or not. A workflow's
invocations are listed as `azathoth workflow invocations` lists them, and
one is resumed as `azathoth invocation resume` resumes it. Who may read or
resume which invocation is for the caller to decide; the API reads any it
is asked for.
"""

import asyncio
from typing import Literal
from uuid import UUID

from pydantic import JsonValue

from azathoth.api.browsing import LIMIT_MESSAGE, RepositoriesAccess
from azathoth.api.errors import ConflictError, InvalidArgumentError, NotFoundError
from azathoth.api.models import (
    InvocationDetail,
    InvocationError,
    InvocationFinished,
    InvocationOutcome,
    InvocationRun,
    InvocationSummary,
    RunStarted,
    RunStep,
)
from azathoth.api.running import (
    CancellationToken,
    EventCallback,
    RuntimeAccess,
    _CallbackObserver,
    _until_cancelled,
    step_status,
)
from azathoth.context import context_sensitivity
from azathoth.telemetry import NO_TELEMETRY, Telemetry
from azathoth.telemetry.invocations import traced_invocation
from azathoth.telemetry.runs import tracing_runner
from azathoth.workflows import (
    ProductionInvocation,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationResumeError,
    ProductionInvocationSuccess,
    WorkflowRun,
    journal_resumes,
    resume_production_invocation,
)
from azathoth.workflows.production_invocation import PRODUCTION_INVOCATION_EVENT_TYPE


class Invocations:
    """The invocations of an instance's promoted workflows."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        runtime: RuntimeAccess | None = None,
        telemetry: Telemetry = NO_TELEMETRY,
    ) -> None:
        """Read the invocations of the repositories `repositories` returns.

        A resumed invocation runs in the runtime `runtime` composes, traced
        by `telemetry`; without a runtime, invocations are read but never
        resumed.
        """

        self._repositories = repositories
        self._runtime = runtime
        self._telemetry = telemetry

    def list(
        self,
        workflow_id: UUID,
        *,
        limit: int | None = None,
    ) -> tuple[InvocationSummary, ...]:
        """Return a workflow's invocations, newest first, as `workflow invocations` lists them.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: The workflow is neither configured nor has invocations.
        """

        if limit is not None and limit < 1:
            raise InvalidArgumentError(LIMIT_MESSAGE)

        repositories = self._repositories()
        invocations = repositories.invocations.invocations_for_workflow(workflow_id)

        if not invocations and not repositories.workflows.revisions(workflow_id):
            raise NotFoundError(f"Workflow {workflow_id} is not configured.")

        newest_first = sorted(
            invocations,
            key=lambda invocation: invocation.created_at,
            reverse=True,
        )

        summaries = []

        for invocation in newest_first[:limit]:
            outcome = repositories.invocations.result(invocation.id)
            association = repositories.invocation_runs.get(invocation.id)

            summaries.append(
                InvocationSummary(
                    invocation_id=invocation.id,
                    workflow_id=invocation.workflow_id,
                    created_at=invocation.created_at,
                    status=_status(outcome),
                    caller_metadata=dict(invocation.caller_metadata),
                    sensitivity=context_sensitivity(invocation.initial_context),
                    run_id=association.run_id if association is not None else None,
                    command=f"azathoth invocation show {invocation.id}",
                )
            )

        return tuple(summaries)

    def resume(
        self,
        invocation_id: UUID,
        *,
        on_event: EventCallback | None = None,
        cancel: CancellationToken | None = None,
    ) -> InvocationOutcome:
        """Resume an incomplete invocation from its journal, as `azathoth invocation resume` does.

        It resumes from the production state it started from, and its run
        from its journal under the same run ID. Events report the run as
        `runs.invoke` reports one, and `invocation_finished` ends the call.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No invocation has this ID.
            ConflictError: It has already completed, or cannot be resumed.
            RunCancelledError: The token was cancelled before it finished;
                it can be resumed again.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        repositories = self._repositories()
        invocation = repositories.invocations.get(invocation_id)

        if invocation is None:
            raise NotFoundError(f"No invocation {invocation_id} was found.")

        if repositories.invocations.result(invocation_id) is not None:
            raise ConflictError(str(ProductionInvocationResumeError.completed(invocation_id)))

        assert self._runtime is not None, "An instance resumes invocations with a runtime."

        runtime = self._runtime(repositories)
        observer = _CallbackObserver(on_event)
        runner = tracing_runner(
            self._telemetry,
            observer=observer,
            journal=repositories.run_journal,
            leases=repositories.run_leases,
            children=repositories.run_children,
            content=repositories.tool_content,
        )

        observer.emit(RunStarted(workflow_id=invocation.workflow_id))

        try:
            with traced_invocation(self._telemetry, workflow_id=invocation.workflow_id) as trace:
                result = asyncio.run(
                    _until_cancelled(
                        resume_production_invocation(
                            invocation=invocation,
                            revisions=repositories.production_revisions.revisions_for_workflow(
                                invocation.workflow_id
                            ),
                            current_state=runtime.production_state(invocation.workflow_id),
                            catalog=runtime.models,
                            registry=runtime.language_models,
                            portfolio=runtime.portfolio,
                            runner=runner,
                            journal=repositories.run_journal,
                            run_repository=repositories.runs,
                            invocation_repository=repositories.invocations,
                            invocation_run_repository=repositories.invocation_runs,
                            tool_resolver=runtime.tool_resolver,
                            tool_implementation_resolver=runtime.tool_implementation_resolver,
                        ),
                        cancel,
                    )
                )

                trace.record(result)
        except ProductionInvocationResumeError as exc:
            raise ConflictError(str(exc)) from exc

        outcome = _resumed_outcome(invocation, result, warnings=())

        observer.emit(InvocationFinished(invocation_id=invocation.id, status=outcome.status))

        return outcome.model_copy(update={"warnings": tuple(observer.warnings)})

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


def _status(
    outcome: ProductionInvocationResult | None,
) -> Literal["succeeded", "failed", "incomplete"]:
    """Return how an invocation ended, or `incomplete` while it has no outcome."""

    if isinstance(outcome, ProductionInvocationSuccess):
        return "succeeded"

    if isinstance(outcome, ProductionInvocationFailure):
        return "failed"

    return "incomplete"


def _resumed_outcome(
    invocation: ProductionInvocation,
    result: ProductionInvocationResult,
    *,
    warnings: tuple[str, ...],
) -> InvocationOutcome:
    """Return the API's view of how a resumed invocation ended."""

    failure = result if isinstance(result, ProductionInvocationFailure) else None

    return InvocationOutcome(
        status="failed" if failure is not None else "succeeded",
        replayed=False,
        idempotency_key=invocation.idempotency.key if invocation.idempotency else "",
        invocation_id=invocation.id,
        result=result.result if isinstance(result, ProductionInvocationSuccess) else None,
        error=(
            InvocationError(
                code=failure.error_code.value,
                message=failure.message,
                metadata=dict(failure.metadata),
            )
            if failure is not None
            else None
        ),
        warnings=warnings,
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

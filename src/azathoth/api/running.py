"""Running and invoking workflows, and watching them run (ADR 0120).

`run` is what `azathoth workflow run` does: the workflow's latest revision
runs as configured, not as promoted, and the finished run is kept as
evidence whether it succeeded or failed. `invoke` is what `azathoth job run`
does: the workflow's active production state runs under an idempotency key,
so the same request again replays its outcome, or resumes it.

Each call returns when it has finished. While it runs, an optional callback
receives each event on the caller's thread, and an optional cancellation
token stops it.
"""

import asyncio
import threading
from collections.abc import Callable, Coroutine, Mapping
from typing import Any, Final, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import JsonValue

from azathoth.api.browsing import RepositoriesAccess
from azathoth.api.catalog import DirectoriesAccess, discover
from azathoth.api.errors import (
    InvalidArgumentError,
    NotFoundError,
    RunCancelledError,
    RunNotStartedError,
)
from azathoth.api.models import (
    ContextChanged,
    InvocationError,
    InvocationFinished,
    InvocationOutcome,
    RunError,
    RunEvent,
    RunFinished,
    RunInput,
    RunResult,
    RunStarted,
    StepFinished,
    StepStarted,
)
from azathoth.context import Context
from azathoth.inputs import (
    JSON_MEDIA_TYPE,
    InlineInput,
    InputPolicy,
    InputProvenance,
    ResolvedInput,
)
from azathoth.jobs import (
    InvokeJobRequest,
    JobResult,
    JobStatus,
    run_invoke_job,
    runtime_job_invoker,
    runtime_job_resumer,
)
from azathoth.persistence.repositories import Repositories
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolioLoader,
)
from azathoth.runtime import AzathothRuntime
from azathoth.telemetry import NO_TELEMETRY
from azathoth.telemetry.runs import tracing_runner
from azathoth.tools import ToolCatalogLoader
from azathoth.workflows import (
    InvocationIdempotency,
    ProductionInvocationResult,
    WorkflowCatalogLoader,
    WorkflowGenerationError,
    WorkflowResultError,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowSpecification,
    WorkflowStepFailure,
    WorkflowStepStarted,
    WorkflowStepStatus,
    create_workflow_input_events,
    validate_idempotency_key,
    workflow_result,
)

RUN_PRODUCER: Final = "azathoth.api"
"""The producer of the input event a run given input starts with."""

CANCEL_POLL_SECONDS: Final = 0.05
"""How often a running workflow checks its cancellation token."""

GENERATED_KEY_PREFIX: Final = "api-"
"""What begins the idempotency key an invocation is given when it names none."""

INLINE_ONLY: Final = InputPolicy()
"""An invocation's input is the value given: no reference is resolved."""

EventCallback = Callable[[RunEvent], None]
"""Receive one run event, on the run's thread; it must return quickly."""

RunT = TypeVar("RunT", WorkflowRun, JobResult)
"""What a cancellable call finishes with: a run, or a job's result."""

LanguageModelsAccess = Callable[[ModelCatalog], LanguageModelRegistry]
"""Return the executable models an instance's providers serve, for the models discovered."""


class CancellationToken:
    """Stop a run from another thread, as a stop button does.

    Cancelling stops the run where it is, as Ctrl-C stops `azathoth workflow
    run`: its lease is released, and its journal can be resumed. A token
    cancelled before the run starts stops it before anything runs.
    """

    def __init__(
        self,
    ) -> None:
        """Make a token that has not been cancelled."""

        self._cancelled = threading.Event()

    def cancel(
        self,
    ) -> None:
        """Ask the run to stop; asking again changes nothing."""

        self._cancelled.set()

    @property
    def cancelled(
        self,
    ) -> bool:
        """Return whether the run was asked to stop."""

        return self._cancelled.is_set()


class _CallbackObserver:
    """Turn the runner's step events into API events for one callback.

    The runner discards what an observer raises, so the observer catches it
    itself: a callback that raises is detached for the rest of the run, and
    its failure becomes a warning on the result.
    """

    def __init__(
        self,
        callback: EventCallback | None,
    ) -> None:
        self._callback = callback
        self.warnings: list[str] = []

    def emit(
        self,
        event: RunEvent,
    ) -> None:
        """Deliver one event, detaching the callback if it raises."""

        if self._callback is None:
            return

        try:
            self._callback(event)
        except Exception as exc:
            self._callback = None
            self.warnings.append(
                f"The event callback raised {type(exc).__name__}: {exc}, and was detached."
            )

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Deliver the API's events for one of the runner's."""

        if isinstance(event, WorkflowStepStarted):
            self.emit(
                StepStarted(
                    step_id=event.step.id,
                    layer=event.layer_index,
                    message=event.step.message,
                )
            )

            return

        self.emit(
            StepFinished(
                step_id=event.step.id,
                layer=event.layer_index,
                status=_status(event.status),
                failure=_failure_message(event.failure),
                confidence=event.confidence,
            )
        )

        if event.values:
            self.emit(
                ContextChanged(
                    step_id=event.step.id,
                    values={value.name: value.value for value in event.values},
                )
            )


def _status(
    status: WorkflowStepStatus,
) -> Literal["executed", "failed", "skipped"]:
    """Return a step status as the API names it."""

    if status is WorkflowStepStatus.EXECUTED:
        return "executed"

    if status is WorkflowStepStatus.FAILED:
        return "failed"

    return "skipped"


def _failure_message(
    failure: WorkflowStepFailure | None,
) -> str | None:
    """Return the message of a step's final failure, if it failed."""

    return failure.message if failure is not None else None


class Runs:
    """Runs of an instance's configured workflows."""

    def __init__(
        self,
        repositories: RepositoriesAccess,
        directories: DirectoriesAccess,
        language_models: LanguageModelsAccess,
    ) -> None:
        """Run workflows over the repositories and providers given."""

        self._repositories = repositories
        self._directories = directories
        self._language_models = language_models

    def run(
        self,
        workflow_id: UUID,
        *,
        input: RunInput | None = None,
        on_event: EventCallback | None = None,
        cancel: CancellationToken | None = None,
    ) -> RunResult:
        """Run a workflow's latest revision as configured, and keep the finished run.

        A run given input starts with it as its workflow input event; a run
        given none starts with an empty context. The run is kept whether it
        succeeded or failed, and its result says which.

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No workflow has this ID.
            RunNotStartedError: No executable candidate could be made, for
                example because a step's tool or model is not available.
            RunCancelledError: The token was cancelled before the run finished.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        if cancel is not None and cancel.cancelled:
            raise RunCancelledError()

        repositories = self._repositories()
        runtime = self._runtime(repositories)
        specification = runtime.workflows.get(workflow_id)

        if specification is None:
            raise NotFoundError(f"Workflow {workflow_id} is not configured.")

        try:
            candidate = runtime.generate_workflow_candidate(workflow_id)
        except WorkflowGenerationError as exc:
            raise RunNotStartedError(str(exc)) from exc

        observer = _CallbackObserver(on_event)
        runner = tracing_runner(
            NO_TELEMETRY,
            observer=observer,
            journal=repositories.run_journal,
            leases=repositories.run_leases,
            children=repositories.run_children,
            content=repositories.tool_content,
        )

        observer.emit(RunStarted(workflow_id=workflow_id))

        run = asyncio.run(
            _until_cancelled(
                runner.run_recording_failures(candidate, _context(input)),
                cancel,
            )
        )

        repositories.runs.save(run)

        has_result, value, error = _outcome(run, specification)

        observer.emit(RunFinished(run_id=run.id, succeeded=error is None))

        return RunResult(
            run_id=run.id,
            workflow_id=workflow_id,
            workflow_revision=run.workflow_revision,
            succeeded=error is None,
            has_result=has_result,
            result=value,
            error=error,
            warnings=tuple(observer.warnings),
            started_at=run.started_at,
            completed_at=run.completed_at,
            command=f"azathoth run show {run.id}",
        )

    def invoke(
        self,
        workflow_id: UUID,
        *,
        input: JsonValue,
        idempotency_key: str | None = None,
        caller_metadata: Mapping[str, JsonValue] | None = None,
        on_event: EventCallback | None = None,
        cancel: CancellationToken | None = None,
    ) -> InvocationOutcome:
        """Invoke a workflow's active production state under an idempotency key.

        As `azathoth job run` does: a key recorded with the same request
        replays its outcome; a key recorded with another request is
        rejected as an `idempotency_conflict`; an invocation whose run was
        stopped is resumed from its journal. Without a key, one beginning
        `api-` is made. A workflow not in production, or that fails, is an
        outcome, not an error. The caller metadata is recorded with the
        invocation.

        Events report the run as it happens, and `invocation_finished` ends
        every call, including a replay or a rejection.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The idempotency key is empty, too long or
                holds a control character.
            RunCancelledError: The token was cancelled before the invocation
                finished; the same request under the same key resumes it.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        if cancel is not None and cancel.cancelled:
            raise RunCancelledError()

        key = idempotency_key if idempotency_key is not None else f"{GENERATED_KEY_PREFIX}{uuid4()}"

        try:
            validate_idempotency_key(key)
        except ValueError as exc:
            raise InvalidArgumentError(str(exc)) from exc

        repositories = self._repositories()
        observer = _CallbackObserver(on_event)
        runner = tracing_runner(
            NO_TELEMETRY,
            observer=observer,
            journal=repositories.run_journal,
            leases=repositories.run_leases,
            children=repositories.run_children,
            content=repositories.tool_content,
        )

        def load_runtime() -> AzathothRuntime:
            return self._runtime(repositories)

        invoker = runtime_job_invoker(
            load_runtime,
            invocation_repository=repositories.invocations,
            run_repository=repositories.runs,
            invocation_run_repository=repositories.invocation_runs,
            runner=runner,
        )

        async def invoke(
            *,
            workflow_id: UUID,
            payload: JsonValue,
            caller_metadata: Mapping[str, JsonValue],
            input_provenance: InputProvenance | None,
            idempotency: InvocationIdempotency,
        ) -> ProductionInvocationResult:
            observer.emit(RunStarted(workflow_id=workflow_id))

            return await invoker(
                workflow_id=workflow_id,
                payload=payload,
                caller_metadata=caller_metadata,
                input_provenance=input_provenance,
                idempotency=idempotency,
            )

        job = asyncio.run(
            _until_cancelled(
                run_invoke_job(
                    InvokeJobRequest(
                        kind="invoke",
                        version=1,
                        idempotency_key=key,
                        workflow_id=workflow_id,
                        input=InlineInput(value=input),
                        caller_metadata=dict(caller_metadata or {}),
                    ),
                    policy=INLINE_ONLY,
                    store=repositories.content,
                    invocation_repository=repositories.invocations,
                    invoke=invoke,
                    resume=runtime_job_resumer(
                        load_runtime,
                        invocation_repository=repositories.invocations,
                        run_repository=repositories.runs,
                        invocation_run_repository=repositories.invocation_runs,
                        revision_repository=repositories.production_revisions,
                        journal=repositories.run_journal,
                        runner=runner,
                    ),
                ),
                cancel,
            )
        )

        outcome = _invocation_outcome(job, key, warnings=())

        observer.emit(
            InvocationFinished(invocation_id=outcome.invocation_id, status=outcome.status)
        )

        return outcome.model_copy(update={"warnings": tuple(observer.warnings)})

    def _runtime(
        self,
        repositories: Repositories,
    ) -> AzathothRuntime:
        """Compose the runtime a run needs, as the command line does."""

        models = discover(repositories, self._directories())
        tool_loader = ToolCatalogLoader(repositories.tools)

        return AzathothRuntime(
            workflows=WorkflowCatalogLoader(repositories.workflows).load_catalog(),
            production_states=repositories.production_states.states(),
            models=models,
            portfolio=ModelPortfolioLoader(repositories.portfolio).load_portfolio(),
            language_models=self._language_models(models),
            tools=tool_loader.load_catalog(),
            tool_implementations=tool_loader.load_implementation_catalog(),
            judges=repositories.judges.rotation(),
        )


async def _until_cancelled(
    run: Coroutine[Any, Any, RunT],
    cancel: CancellationToken | None,
) -> RunT:
    """Await a run, cancelling it as soon as its token is cancelled.

    Raises:
        RunCancelledError: The token was cancelled before the run finished.
    """

    task = asyncio.ensure_future(run)

    if cancel is None:
        return await task

    while not task.done():
        if cancel.cancelled:
            task.cancel()

            try:
                return await task
            except asyncio.CancelledError:
                raise RunCancelledError() from None

        await asyncio.wait({task}, timeout=CANCEL_POLL_SECONDS)

    return task.result()


def _invocation_status(
    status: JobStatus,
) -> Literal["succeeded", "failed", "rejected", "incomplete"]:
    """Return a job's status as the API names it."""

    if status is JobStatus.SUCCEEDED:
        return "succeeded"

    if status is JobStatus.FAILED:
        return "failed"

    if status is JobStatus.REJECTED:
        return "rejected"

    return "incomplete"


def _invocation_outcome(
    job: JobResult,
    key: str,
    *,
    warnings: tuple[str, ...],
) -> InvocationOutcome:
    """Return the API's view of one job's result."""

    return InvocationOutcome(
        status=_invocation_status(job.status),
        replayed=job.replayed,
        idempotency_key=key,
        invocation_id=job.invocation_id,
        result=job.result,
        error=(
            InvocationError(
                code=job.error.code.value,
                message=job.error.message,
                metadata=job.error.metadata,
            )
            if job.error is not None
            else None
        ),
        warnings=warnings,
        command=(
            f"azathoth invocation show {job.invocation_id}"
            if job.invocation_id is not None
            else None
        ),
    )


def _context(
    run_input: RunInput | None,
) -> Context:
    """Return the context a run starts with: its input event, or nothing."""

    if run_input is None:
        return Context()

    return Context(
        events=create_workflow_input_events(
            ResolvedInput(value=run_input.payload, media_type=JSON_MEDIA_TYPE),
            producer=RUN_PRODUCER,
        )
    )


def _outcome(
    run: WorkflowRun,
    specification: WorkflowSpecification,
) -> tuple[bool, JsonValue, RunError | None]:
    """Return whether a finished run has its result, the result, and why not.

    As `azathoth workflow run` reports it: a run that halted names the step
    that halted it and its final failure; a run that finished without
    producing its declared result says so; a run without a declared result
    succeeded with none.
    """

    if run.failed:
        failed = next(
            step
            for step in run.steps
            if step.status is WorkflowStepStatus.FAILED
            and (run.halting_step_id is None or step.step_id == run.halting_step_id)
        )
        failure = failed.attempts[-1].failure

        return (
            False,
            None,
            RunError(
                code="workflow_execution_failed",
                step_id=failed.step_id,
                exception_type=failure.exception_type if failure is not None else None,
                message=failure.message if failure is not None else "The step failed.",
            ),
        )

    if specification.result is None:
        return False, None, None

    try:
        value = workflow_result(run, specification.result, steps=specification.steps)
    except WorkflowResultError as exc:
        return (
            False,
            None,
            RunError(
                code="result_not_produced",
                step_id=None,
                exception_type=None,
                message=str(exc),
            ),
        )

    return True, value, None


__all__ = [
    "CANCEL_POLL_SECONDS",
    "GENERATED_KEY_PREFIX",
    "RUN_PRODUCER",
    "CancellationToken",
    "EventCallback",
    "Runs",
]

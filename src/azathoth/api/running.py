"""Running workflows and watching them run (ADR 0120).

A run here is what `azathoth workflow run` does: the workflow's latest
revision runs as configured, not as promoted, and the finished run is kept
as evidence whether it succeeded or failed. The call returns when the run
has finished. While it runs, an optional callback receives each event on the
caller's thread, and an optional cancellation token stops it.
"""

import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import Any, Final, Literal
from uuid import UUID

from pydantic import JsonValue

from azathoth.api.browsing import RepositoriesAccess
from azathoth.api.catalog import DirectoriesAccess, discover
from azathoth.api.errors import (
    NotFoundError,
    RunCancelledError,
    RunNotStartedError,
)
from azathoth.api.models import (
    ContextChanged,
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
from azathoth.inputs import JSON_MEDIA_TYPE, ResolvedInput
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
    workflow_result,
)

RUN_PRODUCER: Final = "azathoth.api"
"""The producer of the input event a run given input starts with."""

CANCEL_POLL_SECONDS: Final = 0.05
"""How often a running workflow checks its cancellation token."""

EventCallback = Callable[[RunEvent], None]
"""Receive one run event, on the run's thread; it must return quickly."""

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
    run: Coroutine[Any, Any, WorkflowRun],
    cancel: CancellationToken | None,
) -> WorkflowRun:
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
    "RUN_PRODUCER",
    "CancellationToken",
    "EventCallback",
    "Runs",
]

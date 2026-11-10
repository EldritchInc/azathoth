"""Running and invoking workflows, and watching them run (ADR 0120).

`run` is what `azathoth workflow run` does: the workflow's latest revision
runs as configured, not as promoted, and the finished run is kept as
evidence whether it succeeded or failed. `invoke` is what `azathoth job run`
does: the workflow's active production state runs under an idempotency key,
so the same request again replays its outcome, or resumes it.

Either may be given a file as its input, checked and kept as the command
line's `--input-file` is (ADR 0121).

Each call returns when it has finished. While it runs, an optional callback
receives each event on the caller's thread, and an optional cancellation
token stops it.
"""

import asyncio
import base64
import json
import threading
from collections.abc import Callable, Coroutine, Mapping
from typing import Any, Final, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import JsonValue

from azathoth.api.browsing import Document, RepositoriesAccess
from azathoth.api.catalog import DirectoriesAccess, discover
from azathoth.api.errors import (
    InvalidArgumentError,
    InvalidDocumentError,
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
    RunFile,
    RunFinished,
    RunInput,
    RunResult,
    RunStarted,
    StepFinished,
    StepKind,
    StepReadiness,
    StepStarted,
    WorkflowReadiness,
)
from azathoth.context import Context
from azathoth.inputs import (
    DEFAULT_MAX_INPUT_BYTES,
    JSON_MEDIA_TYPE,
    ContentStore,
    InlineInput,
    InputContentError,
    InputPolicy,
    InputProvenance,
    InputResolutionError,
    ResolvedInput,
    check_binary_signature,
    decode_content,
    is_binary_media_type,
    resolve_inline_input,
    validate_media_type,
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
from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    FixedModelSelection,
    ModelSelection,
    PromptStrategy,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolioLoader,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import Strategy
from azathoth.telemetry import Telemetry
from azathoth.telemetry.invocations import traced_job_invoker
from azathoth.telemetry.runs import tracing_runner
from azathoth.tools import ToolCatalogLoader, ToolStrategy
from azathoth.workflows import (
    InvocationIdempotency,
    ProductionInvocationResult,
    ToolStepSpecification,
    WorkflowCatalogLoader,
    WorkflowDocumentError,
    WorkflowGenerationError,
    WorkflowResultError,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowSpecification,
    WorkflowStepFailure,
    WorkflowStepSpecification,
    WorkflowStepStarted,
    WorkflowStepStatus,
    create_workflow_input_events,
    decode_workflow_document,
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

MAX_INPUT_FILE_BYTES: Final = DEFAULT_MAX_INPUT_BYTES
"""The largest file a run or an invocation is given, as for `--input-file`."""

INPUT_FILE_NAME: Final = "The input file"
"""What a refusal of a file given as input calls it."""

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
                status=step_status(event.status),
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


def step_status(
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
        telemetry: Telemetry,
    ) -> None:
        """Run workflows over the repositories and providers given, traced by `telemetry`."""

        self._repositories = repositories
        self._directories = directories
        self._language_models = language_models
        self._telemetry = telemetry

    def run(
        self,
        workflow_id: UUID,
        *,
        input: RunInput | RunFile | None = None,
        on_event: EventCallback | None = None,
        cancel: CancellationToken | None = None,
    ) -> RunResult:
        """Run a workflow's latest revision as configured, and keep the finished run.

        A run given input starts with it as its workflow input event; a run
        given none starts with an empty context. A file given as input is
        checked before anything else, and kept in the content store when it
        is binary. The run is kept whether it succeeded or failed, and its
        result says which.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: A file given as input is not its media
                type, is of one Azathoth does not accept, or is too large.
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

        source = file_input(input) if isinstance(input, RunFile) else input
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
            self._telemetry,
            observer=observer,
            journal=repositories.run_journal,
            leases=repositories.run_leases,
            children=repositories.run_children,
            content=repositories.tool_content,
        )

        observer.emit(RunStarted(workflow_id=workflow_id))

        run = asyncio.run(
            _until_cancelled(
                runner.run_recording_failures(candidate, _context(source, repositories.content)),
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
        input: JsonValue | RunFile,
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
        invocation. A file given as input is checked before anything is
        recorded, and is part of the request its key is recorded with.

        Events report the run as it happens, and `invocation_finished` ends
        every call, including a replay or a rejection.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The idempotency key is empty, too long or
                holds a control character, or a file given as input is not
                its media type, is of one Azathoth does not accept, or is too
                large.
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

        request_input = (
            file_input(input) if isinstance(input, RunFile) else InlineInput(value=input)
        )

        repositories = self._repositories()
        observer = _CallbackObserver(on_event)
        runner = tracing_runner(
            self._telemetry,
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
                        input=request_input,
                        caller_metadata=dict(caller_metadata or {}),
                    ),
                    policy=INLINE_ONLY,
                    store=repositories.content,
                    invocation_repository=repositories.invocations,
                    invoke=traced_job_invoker(self._telemetry, invoke),
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

    def readiness(
        self,
        document: Document,
    ) -> WorkflowReadiness:
        """Return whether each step of a workflow document could run here now.

        The providers are asked what they serve, as a run asks them, and
        each step is resolved as a run resolves it: a prompt step to the
        models it could run on, in the order a run tries them, and a tool
        step to the implementation it would run. Nothing is saved, and the
        document need not have been imported.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidDocumentError: It is not a workflow document.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        repositories = self._repositories()

        try:
            specification = decode_workflow_document(
                document if isinstance(document, str) else json.dumps(dict(document))
            )
        except WorkflowDocumentError as exc:
            raise InvalidDocumentError(str(exc)) from exc

        runtime = self._runtime(repositories)
        steps = tuple(_step_readiness(step, runtime) for step in specification.steps)

        return WorkflowReadiness(
            ready=all(step.ready for step in steps),
            steps=steps,
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


NO_PORTFOLIO_MESSAGE: Final = "The portfolio authorizes no model."
"""Why a step that chooses its model has none to choose from."""

NO_MATCH_MESSAGE: Final = "No model in the portfolio meets what this step needs."
"""Why a step that chooses its model finds none that meets its needs."""


def _step_kind(
    step: WorkflowStepSpecification,
) -> StepKind:
    """Return how a step runs."""

    if isinstance(step.specification, ToolStepSpecification):
        return "tool"

    if isinstance(step.specification, ContextPromptStrategySpec):
        return "context_prompt"

    return "prompt"


def _model_of(
    strategy: Strategy,
) -> str | None:
    """Return the model a prompt strategy runs on, or `None` for any other strategy."""

    if isinstance(strategy, PromptStrategy | ContextPromptStrategy):
        binding = strategy.model_binding

        return binding.identifier if binding is not None else None

    return None


def _no_model(
    selection: ModelSelection,
    runtime: AzathothRuntime,
) -> str:
    """Return why a prompt step choosing its model as `selection` says has none to run on."""

    if isinstance(selection, FixedModelSelection):
        if runtime.models.get(selection.identifier) is None:
            return f"Model {selection.identifier!r} is not currently available."

        return f"Model {selection.identifier!r} is served, but cannot be run here."

    if not runtime.portfolio.entries:
        return NO_PORTFOLIO_MESSAGE

    return NO_MATCH_MESSAGE


def _step_readiness(
    step: WorkflowStepSpecification,
    runtime: AzathothRuntime,
) -> StepReadiness:
    """Return whether one step could run here now, and on what."""

    kind = _step_kind(step)
    unready = StepReadiness(
        step_id=step.id,
        kind=kind,
        ready=False,
        models=(),
        tool_id=None,
        tool_version=None,
        tool_implementation_id=None,
        problem=None,
    )

    try:
        strategies = runtime.generate_step_strategies(step)
    except WorkflowGenerationError as exc:
        return unready.model_copy(update={"problem": str(exc)})

    specification = step.specification

    if isinstance(specification, ToolStepSpecification):
        [tool] = strategies

        assert isinstance(tool, ToolStrategy)

        implementation = tool.implementation

        return unready.model_copy(
            update={
                "ready": True,
                "tool_id": implementation.tool_id,
                "tool_version": implementation.tool_version,
                "tool_implementation_id": implementation.id,
            }
        )

    models = tuple(
        model for model in (_model_of(strategy) for strategy in strategies) if model is not None
    )

    if not models:
        return unready.model_copy(
            update={"problem": _no_model(specification.model_selection, runtime)}
        )

    return unready.model_copy(update={"ready": True, "models": models})


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


def file_input(
    run_file: RunFile,
    *,
    max_bytes: int = MAX_INPUT_FILE_BYTES,
) -> InlineInput:
    """Return the inline input a file stands for, checked as `--input-file` is (ADR 0121).

    JSON and text content is decoded into its value. Binary content is
    checked against its media type's signature, and stands as base64 until
    it is resolved and kept (ADR 0112).

    Raises:
        InvalidArgumentError: The media type is not one Azathoth accepts, the
            content is larger than `max_bytes`, or it is not its media type.
    """

    try:
        media_type = validate_media_type(run_file.media_type)
    except ValueError as exc:
        raise InvalidArgumentError(str(exc)) from exc

    if len(run_file.content) > max_bytes:
        raise InvalidArgumentError(
            f"{INPUT_FILE_NAME} is larger than the limit of {max_bytes} bytes."
        )

    try:
        if is_binary_media_type(media_type):
            check_binary_signature(run_file.content, media_type)

            return InlineInput(
                value=base64.b64encode(run_file.content).decode("ascii"),
                media_type=media_type,
            )

        return InlineInput(
            value=decode_content(run_file.content, media_type),
            media_type=media_type,
        )
    except InputContentError as exc:
        raise InvalidArgumentError(str(exc)) from exc


def _context(
    run_input: RunInput | InlineInput | None,
    store: ContentStore,
) -> Context:
    """Return the context a run starts with: its input events, or nothing.

    A file's input is resolved as an inline input is, so a binary one is
    kept in the store, and its provenance follows the input event.
    """

    if run_input is None:
        return Context()

    if isinstance(run_input, RunInput):
        resolved = ResolvedInput(value=run_input.payload, media_type=JSON_MEDIA_TYPE)
    else:
        try:
            resolved = resolve_inline_input(run_input, policy=INLINE_ONLY, store=store)
        except InputResolutionError as exc:
            raise InvalidArgumentError(str(exc)) from exc

    return Context(events=create_workflow_input_events(resolved, producer=RUN_PRODUCER))


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
    "INPUT_FILE_NAME",
    "MAX_INPUT_FILE_BYTES",
    "RUN_PRODUCER",
    "CancellationToken",
    "EventCallback",
    "Runs",
    "file_input",
    "step_status",
]

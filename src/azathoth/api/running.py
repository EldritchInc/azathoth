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

from azathoth.api.browsing import LIMIT_MESSAGE, Document, RepositoriesAccess
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
    RunDetail,
    RunError,
    RunEvent,
    RunFile,
    RunFinished,
    RunInput,
    RunResult,
    RunStarted,
    RunStepDetail,
    RunSummary,
    StepFailure,
    StepFinished,
    StepKind,
    StepMetrics,
    StepReadiness,
    StepStarted,
    StepTrial,
    WorkflowReadiness,
)
from azathoth.context import Context, create_input_sensitivity_event
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
from azathoth.sensitivity import Sensitivity
from azathoth.strategies import Strategy
from azathoth.telemetry import Telemetry
from azathoth.telemetry.invocations import traced_job_invoker
from azathoth.telemetry.runs import tracing_runner
from azathoth.tools import ToolCatalogLoader, ToolStrategy
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    InvocationIdempotency,
    ProductionInvocationResult,
    ToolStepSpecification,
    WorkflowCandidate,
    WorkflowCatalogLoader,
    WorkflowConstantValue,
    WorkflowDocumentError,
    WorkflowGenerationError,
    WorkflowInputBinding,
    WorkflowNamedValueReference,
    WorkflowResultError,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowSpecificationRevision,
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStarted,
    WorkflowStepStatus,
    WorkflowValueReference,
    create_workflow_input_events,
    decode_workflow_document,
    generate_workflow_candidate,
    journal_resumes,
    validate_idempotency_key,
    workflow_result,
)

SENSITIVITY_WITHOUT_INPUT_MESSAGE: Final = "A sensitivity labels a run's input; give input too."
"""What a run given a label but no input is refused with (ADR 0123)."""

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
        sensitivity: Sensitivity | None = None,
        on_event: EventCallback | None = None,
        cancel: CancellationToken | None = None,
    ) -> RunResult:
        """Run a workflow's latest revision as configured, and keep the finished run.

        A run given input starts with it as its workflow input event; a run
        given none starts with an empty context. A file given as input is
        checked before anything else, and kept in the content store when it
        is binary. The input is labelled `sensitivity` when it is given
        (ADR 0123). The run is kept whether it succeeded or failed, and its
        result says which.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: A file given as input is not its media
                type, is of one Azathoth does not accept, or is too large,
                or a sensitivity is given without input.
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

        if sensitivity is not None and input is None:
            raise InvalidArgumentError(SENSITIVITY_WITHOUT_INPUT_MESSAGE)

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
                runner.run_recording_failures(
                    candidate,
                    _context(source, repositories.content, sensitivity),
                ),
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
        sensitivity: Sensitivity | None = None,
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
        recorded, and is part of the request its key is recorded with, as
        the input's `sensitivity` is when it is given (ADR 0123).

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

        unlabelled = file_input(input) if isinstance(input, RunFile) else InlineInput(value=input)
        request_input = unlabelled.model_copy(update={"sensitivity": sensitivity})

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
            sensitivity: Sensitivity | None,
            idempotency: InvocationIdempotency,
        ) -> ProductionInvocationResult:
            observer.emit(RunStarted(workflow_id=workflow_id))

            return await invoker(
                workflow_id=workflow_id,
                payload=payload,
                caller_metadata=caller_metadata,
                input_provenance=input_provenance,
                sensitivity=sensitivity,
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

    def list(
        self,
        workflow_id: UUID,
        *,
        limit: int | None = None,
    ) -> tuple[RunSummary, ...]:
        """Return a workflow's kept runs newest first, at most `limit` of them (ADR 0121).

        A workflow's runs are listed as `azathoth workflow runs` lists them:
        a workflow since removed from configuration keeps its runs. Each is
        judged by the revision that ran. A run that has not finished is not
        kept yet, so it is not listed.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidArgumentError: The limit is below 1.
            NotFoundError: The workflow is neither configured nor has runs.
        """

        if limit is not None and limit < 1:
            raise InvalidArgumentError(LIMIT_MESSAGE)

        repositories = self._repositories()
        runs = repositories.runs.runs_for_workflow(workflow_id)
        history = repositories.workflows.revisions(workflow_id)

        if not runs and not history:
            raise NotFoundError(f"Workflow {workflow_id} is not configured.")

        newest_first = sorted(runs, key=lambda run: run.started_at, reverse=True)[:limit]
        invocations = _invocations(repositories)

        return tuple(
            _summary(run, _judged(run, history), invocations.get(run.id)) for run in newest_first
        )

    def get(
        self,
        run_id: UUID,
    ) -> RunDetail:
        """Return one kept run with its input, its result and each step's evidence (ADR 0121).

        Raises:
            InstanceClosedError: The instance was closed.
            NotFoundError: No run has this ID, or it has not finished.
        """

        repositories = self._repositories()
        run = repositories.runs.get(run_id)
        entries = repositories.run_journal.entries(run_id)

        if run is None:
            raise NotFoundError(
                _unfinished_message(run_id, entries[0].invocation_id)
                if entries
                else f"Run {run_id} was not found."
            )

        has_result, value, error = _judged(run, repositories.workflows.revisions(run.workflow.id))
        summary = _summary(run, (has_result, value, error), _invocations(repositories).get(run.id))
        has_input, given = _run_input(run)

        return RunDetail(
            **summary.model_dump(),
            has_result=has_result,
            result=value,
            has_input=has_input,
            input=given,
            resumes=journal_resumes(entries),
            steps=tuple(_step_detail(step) for step in run.steps),
        )

    def try_step(
        self,
        document: Document,
        step_id: UUID,
        *,
        inputs: Mapping[str, JsonValue | RunFile] | None = None,
        input: RunInput | RunFile | None = None,
        sensitivity: Sensitivity | None = None,
        on_event: EventCallback | None = None,
        cancel: CancellationToken | None = None,
    ) -> StepTrial:
        """Try one step of a workflow document alone, and keep nothing of it (ADR 0121).

        The step runs as a run would run it, on the inputs given: each value
        `inputs` names takes the place of that input's source, a file being
        checked and kept as a run's file is. An input not given keeps its
        source: a constant its value, and a field of the run's input the
        field of `input`. An input taking a value another step produces has
        no step to produce it, so it must be given. `sensitivity` labels
        everything the step is given, `inputs` as well as `input` (ADR 0123).

        The step's conditions are not asked, and it is retried as its retry
        policy says. Its events reach `on_event` as a run's do, without the
        run's own. No run, journal or trace is kept, and the document need
        not have been imported; what the step keeps by its digest in the
        content store, such as a file given, is kept as any run keeps it.

        Raises:
            InstanceClosedError: The instance was closed.
            InvalidDocumentError: It is not a workflow document.
            NotFoundError: The document has no step with this ID.
            InvalidArgumentError: An input given is not one the step takes,
                one another step produces is not given, or a file given is
                not one Azathoth accepts.
            RunNotStartedError: The step could not be made executable, for
                example because its tool or model is not available.
            RunCancelledError: The token was cancelled before the step finished.
            ProviderConfigurationError: A provider is configured in a way
                that cannot be used.
            ProviderUnavailableError: A provider could not be asked.
        """

        if cancel is not None and cancel.cancelled:
            raise RunCancelledError()

        repositories = self._repositories()
        specification = _decoded(document)
        step = next((each for each in specification.steps if each.id == step_id), None)

        if step is None:
            raise NotFoundError(f"The workflow document has no step {step_id}.")

        given = dict(inputs or {})
        _check_inputs(step, given)
        source = file_input(input) if isinstance(input, RunFile) else input
        files = {
            name: file_input(value) for name, value in given.items() if isinstance(value, RunFile)
        }
        runtime = self._runtime(repositories)
        plain = {name: value for name, value in given.items() if not isinstance(value, RunFile)}

        #
        # The step is made executable before a file given is kept, so a
        # step that cannot start keeps nothing.
        #
        _candidate(specification, _alone(step, plain | dict.fromkeys(files)), runtime)

        resolved = {name: _resolved(each, repositories.content) for name, each in files.items()}
        candidate = _candidate(specification, _alone(step, plain | resolved), runtime)

        observer = _CallbackObserver(on_event)
        runner = WorkflowRunner(observer=observer, content=repositories.tool_content)

        run = asyncio.run(
            _until_cancelled(
                runner.run_recording_failures(
                    candidate,
                    _context(source, repositories.content, sensitivity),
                ),
                cancel,
            )
        )

        return StepTrial(
            step=_step_detail(run.steps[0]),
            warnings=tuple(observer.warnings),
        )

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

        specification = _decoded(document)
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


def _decoded(
    document: Document,
) -> WorkflowSpecification:
    """Return the specification a workflow document holds.

    Raises:
        InvalidDocumentError: It is not a workflow document.
    """

    try:
        return decode_workflow_document(
            document if isinstance(document, str) else json.dumps(dict(document))
        )
    except WorkflowDocumentError as exc:
        raise InvalidDocumentError(str(exc)) from exc


def _check_inputs(
    step: WorkflowStepSpecification,
    given: Mapping[str, JsonValue | RunFile],
) -> None:
    """Refuse the inputs given a step tried alone that it could not run on.

    Raises:
        InvalidArgumentError: An input given is not one the step takes, or
            one another step produces is not given.
    """

    names = {binding.name for binding in step.inputs}
    unknown = next((name for name in given if name not in names), None)

    if unknown is not None:
        raise InvalidArgumentError(f"Step {step.id} has no input {unknown!r}.")

    produced = next(
        (
            binding.name
            for binding in step.inputs
            if binding.name not in given
            and isinstance(binding.source, WorkflowValueReference | WorkflowNamedValueReference)
        ),
        None,
    )

    if produced is not None:
        raise InvalidArgumentError(
            f"Step {step.id} input {produced!r} takes a value another step produces, "
            "so trying the step alone needs it given."
        )


def _resolved(
    given: InlineInput,
    store: ContentStore,
) -> JsonValue:
    """Return the value a file given as a step's input stands for, keeping it when binary.

    Raises:
        InvalidArgumentError: The file could not be resolved.
    """

    try:
        return resolve_inline_input(given, policy=INLINE_ONLY, store=store).value
    except InputResolutionError as exc:
        raise InvalidArgumentError(str(exc)) from exc


def _candidate(
    specification: WorkflowSpecification,
    step: WorkflowStepSpecification,
    runtime: AzathothRuntime,
) -> WorkflowCandidate:
    """Return the candidate of a workflow of one step alone, as a run would make it.

    Raises:
        RunNotStartedError: The step could not be made executable.
    """

    try:
        return generate_workflow_candidate(
            WorkflowSpecification(metadata=specification.metadata, steps=(step,)),
            runtime.models,
            runtime.language_models,
            portfolio=runtime.portfolio,
            tool_resolver=runtime.tool_resolver,
            tool_implementation_resolver=runtime.tool_implementation_resolver,
        )
    except WorkflowGenerationError as exc:
        raise RunNotStartedError(str(exc)) from exc


def _alone(
    step: WorkflowStepSpecification,
    values: Mapping[str, JsonValue],
) -> WorkflowStepSpecification:
    """Return a step as it runs alone: on the values given, depending on nothing, unconditioned."""

    return step.model_copy(
        update={
            "depends_on": (),
            "conditions": (),
            "inputs": tuple(
                WorkflowInputBinding(
                    name=binding.name,
                    source=WorkflowConstantValue(value=values[binding.name]),
                )
                if binding.name in values
                else binding
                for binding in step.inputs
            ),
        }
    )


def _unfinished_message(
    run_id: UUID,
    invocation_id: UUID | None,
) -> str:
    """Return what `run show` says of a run that journaled but never finished."""

    if invocation_id is not None:
        return (
            f"Run {run_id} has not finished; resume it with "
            f"azathoth invocation resume {invocation_id}."
        )

    return f"Run {run_id} has not finished; resume it with azathoth run resume {run_id}."


def _invocations(
    repositories: Repositories,
) -> dict[UUID, UUID]:
    """Return the production invocation each run that executed one executed, by run."""

    return {
        association.run_id: association.invocation_id
        for association in repositories.invocation_runs.associations()
    }


def _judged(
    run: WorkflowRun,
    history: tuple[WorkflowSpecificationRevision, ...],
) -> tuple[bool, JsonValue, RunError | None]:
    """Return whether a kept run has its result, the result, and why not, by the revision it ran.

    A run recorded before revisions is judged by the latest. A run of a
    workflow removed from configuration has no declared result to judge it
    by, so it failed only when it halted.
    """

    specification = (
        (history[-1].specification if history else None)
        if run.workflow_revision is None
        else next(
            (
                revision.specification
                for revision in history
                if revision.number == run.workflow_revision
            ),
            None,
        )
    )

    if specification is None:
        return False, None, _halt(run)

    return _outcome(run, specification)


def _summary(
    run: WorkflowRun,
    judged: tuple[bool, JsonValue, RunError | None],
    invocation_id: UUID | None,
) -> RunSummary:
    """Return the API's view of one kept run, as `_judged` judged it."""

    error = judged[2]

    return RunSummary(
        run_id=run.id,
        workflow_id=run.workflow.id,
        workflow_name=run.workflow.name,
        workflow_revision=run.workflow_revision,
        invocation_id=invocation_id,
        succeeded=error is None,
        error=error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        command=f"azathoth run show {run.id}",
    )


def _run_input(
    run: WorkflowRun,
) -> tuple[bool, JsonValue]:
    """Return whether a run was given input, and the input, as its workflow input event holds it.

    A run of a production invocation is given its invocation's input this
    way too.
    """

    for event in run.initial_context.events:
        if event.event_type == WORKFLOW_INPUT_EVENT_TYPE:
            return True, event.payload.get("input")

    return False, None


def _step_detail(
    step: WorkflowStepRun,
) -> RunStepDetail:
    """Return the API's view of one step of a kept run."""

    execution = step.execution
    metrics = execution.metrics if execution is not None else None

    return RunStepDetail(
        step_id=step.step_id,
        status=step_status(step.status),
        attempts=len(step.attempts),
        confidence=step.confidence,
        layer=step.layer_index,
        started_at=step.attempts[0].started_at if step.attempts else None,
        completed_at=step.attempts[-1].completed_at if step.attempts else None,
        strategy=execution.strategy_name if execution is not None else None,
        metrics=(
            StepMetrics(**metrics.model_dump(include=set(StepMetrics.model_fields)))
            if metrics is not None
            else None
        ),
        output=execution.output if execution is not None else None,
        values={value.name: value.value for value in step.values},
        failures=tuple(
            StepFailure(
                attempt=attempt.attempt_number,
                exception_type=attempt.failure.exception_type,
                message=attempt.failure.message,
            )
            for attempt in step.attempts
            if attempt.failure is not None
        ),
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
    sensitivity: Sensitivity | None = None,
) -> Context:
    """Return the context a run starts with: its input events, or nothing.

    A file's input is resolved as an inline input is, so a binary one is
    kept in the store, and its provenance follows the input event. A label
    follows them (ADR 0123); one given without input is recorded alone.
    """

    if run_input is None:
        if sensitivity is None:
            return Context()

        return Context(events=(create_input_sensitivity_event(sensitivity, producer=RUN_PRODUCER),))

    if isinstance(run_input, RunInput):
        resolved = ResolvedInput(value=run_input.payload, media_type=JSON_MEDIA_TYPE)
    else:
        try:
            resolved = resolve_inline_input(run_input, policy=INLINE_ONLY, store=store)
        except InputResolutionError as exc:
            raise InvalidArgumentError(str(exc)) from exc

    labelled = resolved.model_copy(update={"sensitivity": sensitivity})

    return Context(events=create_workflow_input_events(labelled, producer=RUN_PRODUCER))


def _halt(
    run: WorkflowRun,
) -> RunError | None:
    """Return the step that halted a run and its final failure, or None for a run that did not."""

    if not run.failed:
        return None

    failed = next(
        step
        for step in run.steps
        if step.status is WorkflowStepStatus.FAILED
        and (run.halting_step_id is None or step.step_id == run.halting_step_id)
    )
    failure = failed.attempts[-1].failure

    return RunError(
        code="workflow_execution_failed",
        step_id=failed.step_id,
        exception_type=failure.exception_type if failure is not None else None,
        message=failure.message if failure is not None else "The step failed.",
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

    halt = _halt(run)

    if halt is not None:
        return False, None, halt

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
    "SENSITIVITY_WITHOUT_INPUT_MESSAGE",
    "CancellationToken",
    "EventCallback",
    "Runs",
    "file_input",
    "step_status",
]

"""Workflow execution orchestration."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import JsonValue

from azathoth.context import (
    Context,
    ContextEvent,
    RunLineage,
    lineage_of,
    run_lineage,
    running_step,
)
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.prompting import WORKFLOW_INPUT_BOUND_EVENT_TYPE
from azathoth.strategies import Strategy
from azathoth.workflows.attempt import (
    WorkflowStepAttempt,
    WorkflowStepFailure,
)
from azathoth.workflows.candidate import (
    WorkflowCandidate,
    WorkflowCandidateStep,
)
from azathoth.workflows.confidence import step_confidence
from azathoth.workflows.execution import (
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStepStatus,
)
from azathoth.workflows.failure import WorkflowFailurePolicy
from azathoth.workflows.observation import (
    WorkflowRunEvent,
    WorkflowRunObserver,
    WorkflowStepFinished,
    WorkflowStepStarted,
)
from azathoth.workflows.references import (
    declaring_step_ids,
    resolve_named_value,
)
from azathoth.workflows.retry import WorkflowRetryPolicy
from azathoth.workflows.run_children import RunChild, RunChildRepository
from azathoth.workflows.run_journal import (
    JournalAttemptFinished,
    JournalAttemptStarted,
    JournalLayerCommitted,
    JournalRunFinished,
    JournalRunResumed,
    JournalRunStarted,
    RunJournalEntry,
    RunJournalError,
    RunJournalRepository,
    RunJournalWriter,
)
from azathoth.workflows.run_lease import (
    RunLeaseKeeper,
    RunLeasePolicy,
    RunLeaseRepository,
)
from azathoth.workflows.run_resume import (
    RunResumeError,
    RunResumePoint,
    finished_run,
    resume_point,
)
from azathoth.workflows.value import (
    WorkflowConstantValue,
    WorkflowContextReference,
    WorkflowInputResolutionError,
    WorkflowNamedValueReference,
    WorkflowValue,
    WorkflowValueBinding,
    WorkflowValueReference,
)

RetrySleep = Callable[[float], Awaitable[None]]
"""Wait the given number of seconds before a workflow step retry."""


async def _sleep(
    delay: float,
) -> None:
    """Wait the given number of seconds on the running event loop."""

    await asyncio.sleep(delay)


@dataclass(frozen=True)
class _StepOutcome:
    """The retry-exhausted outcome of executing one eligible workflow step."""

    execution: ExecutionResult | None
    attempts: tuple[WorkflowStepAttempt, ...]
    error: Exception | None


@dataclass(frozen=True)
class _LayerStepResult:
    """Temporary result produced while processing one workflow layer."""

    step: WorkflowCandidateStep
    status: WorkflowStepStatus
    step_context: Context | None = None
    execution: ExecutionResult | None = None
    attempts: tuple[WorkflowStepAttempt, ...] = ()
    error: Exception | None = None


@dataclass(frozen=True)
class _WorkflowExecutionResult:
    """Internal workflow execution result with optional propagated failure."""

    run: WorkflowRun
    error: Exception | None = None


class RecordedStepFailure(Exception):
    """A step failure read back from a run's journal, standing in for the original error.

    A resumed run reuses the attempts its journal records, so a step whose
    recorded attempts all failed fails again with what they recorded.
    """

    def __init__(
        self,
        attempt: WorkflowStepAttempt,
    ) -> None:
        failure = attempt.failure
        super().__init__("" if failure is None else failure.message)
        self.exception_type = None if failure is None else failure.exception_type


def _require_invocation(
    entries: Sequence[RunJournalEntry],
    *,
    run_id: UUID,
    invocation_id: UUID | None,
) -> None:
    """Require a run's journal to record the invocation it is resumed for, if one is named.

    Raises:
        RunResumeError: The journal records another invocation, or none.
    """

    if invocation_id is None or not entries:
        return

    recorded = entries[0].invocation_id

    if recorded != invocation_id:
        executes = "no invocation" if recorded is None else f"invocation {recorded}"

        raise RunResumeError(
            run_id,
            f"Run {run_id} executes {executes}, not invocation {invocation_id}.",
        )


def _first_exception(
    group: BaseExceptionGroup[BaseException],
) -> BaseException:
    """Return the exception a layer's task group stopped for.

    A journal entry that could not be recorded is preferred, so the run stops
    with the journal's error rather than a sibling's cancellation.
    """

    leaves: list[BaseException] = []

    def collect(error: BaseException) -> None:
        if isinstance(error, BaseExceptionGroup):
            for inner in error.exceptions:
                collect(inner)
        else:
            leaves.append(error)

    collect(group)

    for leaf in leaves:
        if isinstance(leaf, RunJournalError):
            return leaf

    return leaves[0]


class WorkflowRunner:
    """Execute workflow candidates.

    The eligible steps of each dependency layer execute concurrently. A layer
    commits only after every one of its steps has finished, always in declared
    order, so the recorded run and its final context are identical whatever
    order the steps finish in.

    An optional observer is told live when each step starts and finishes, in
    the order that actually happens. It only watches: the recorded run is the
    same with or without it.

    A run's ID is assigned when it starts. While a step attempt executes,
    its lineage is current (ADR 0104): its run, its depth and its root, read
    from the lineage the initial context records, so anything the step starts
    as a child learns where it came from.

    A runner given a journal repository records each run's journal while it
    executes (ADR 0105): the run's start, each attempt's start and finish,
    each layer's commit, and the run's finish. An entry that cannot be
    recorded stops the run at once with that error, recording nothing more,
    because a run whose journal is incomplete could not be resumed.

    A runner given a lease repository too holds each run's lease while it
    executes: acquired before the run's first entry, renewed from a thread
    of its own, and released when the run ends, however it ends. Once the
    lease is lost, the run stops before its next entry with the
    `RunLeaseLostError`. A lease that cannot be released lapses on its own.

    A runner given a child repository indexes each run started with lineage
    under the run whose step started it, once, as the run starts.
    """

    def __init__(
        self,
        *,
        executor: StrategyExecutor | None = None,
        sleep: RetrySleep | None = None,
        observer: WorkflowRunObserver | None = None,
        journal: RunJournalRepository | None = None,
        leases: RunLeaseRepository | None = None,
        lease_policy: RunLeasePolicy | None = None,
        children: RunChildRepository | None = None,
    ) -> None:
        if leases is not None and journal is None:
            raise ValueError("A runner that leases its runs must journal them.")

        self._executor = executor if executor is not None else StrategyExecutor()
        self._sleep: RetrySleep = sleep if sleep is not None else _sleep
        self._observer = observer
        self._journal = journal
        self._leases = leases
        self._lease_policy = lease_policy if lease_policy is not None else RunLeasePolicy()
        self._children = children

    def _notify(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Deliver one event to the observer, discarding anything it raises.

        A failing observer, such as a progress printer whose pipe closed, must
        never turn into a step failure or cost a run its evidence.
        """

        if self._observer is None:
            return

        with contextlib.suppress(Exception):
            self._observer.observe(event)

    @staticmethod
    def _resolve_values(
        *,
        step: WorkflowCandidateStep,
        execution: ExecutionResult,
    ) -> tuple[WorkflowValue, ...]:
        """Return the declared values of one successful step execution."""

        return tuple(
            WorkflowValue(
                name=binding.name,
                value=binding.resolve(execution.output),
                producer_step_id=step.id,
            )
            for binding in step.outputs
        )

    @staticmethod
    def _resolve_confidence(
        *,
        step_id: UUID,
        confidence: str | None,
        outputs: tuple[WorkflowValueBinding, ...],
        output: JsonValue,
    ) -> float | None:
        """Return the confidence one step execution reports, if it declares one.

        Raises:
            WorkflowValueResolutionError: The confidence output does not
                resolve against the output.
            WorkflowStepConfidenceError: The confidence is not a number from
                0 to 1 (ADR 0098).
        """

        if confidence is None:
            return None

        binding = next(binding for binding in outputs if binding.name == confidence)

        return step_confidence(
            step_id,
            confidence,
            binding.resolve(output),
        )

    @staticmethod
    def _find_workflow_value(
        *,
        completed_steps: list[WorkflowStepRun],
        producer_step_id: UUID,
        name: str,
    ) -> WorkflowValue | None:
        """Return one previously committed workflow value."""

        matches = tuple(
            value
            for step_run in completed_steps
            if step_run.step_id == producer_step_id
            for value in step_run.values
            if value.name == name
        )

        if len(matches) > 1:
            raise RuntimeError(
                "Validated workflow value reference resolved more "
                "than one committed workflow value."
            )

        if not matches:
            return None

        return matches[0]

    @classmethod
    def _conditions_are_satisfied(
        cls,
        *,
        step: WorkflowCandidateStep,
        completed_steps: list[WorkflowStepRun],
    ) -> bool:
        """Return whether all conditions for a workflow step are satisfied."""

        for condition in step.conditions:
            value = cls._find_workflow_value(
                completed_steps=completed_steps,
                producer_step_id=condition.source.producer_step_id,
                name=condition.source.name,
            )

            if value is None:
                return False

            if not condition.matches(value.value):
                return False

        return True

    @classmethod
    def _resolve_input_value(
        cls,
        *,
        source: WorkflowValueReference | WorkflowNamedValueReference,
        step: WorkflowCandidateStep,
        workflow_steps: tuple[WorkflowCandidateStep, ...],
        completed_steps: list[WorkflowStepRun],
    ) -> WorkflowValue | None:
        """Return the committed value an input value reference resolves to.

        A name-only reference resolves among the step's dependencies that
        declare the name, preferring them in workflow step order.
        """

        if isinstance(
            source,
            WorkflowValueReference,
        ):
            return cls._find_workflow_value(
                completed_steps=completed_steps,
                producer_step_id=source.producer_step_id,
                name=source.name,
            )

        return resolve_named_value(
            source.name,
            producer_step_ids=declaring_step_ids(
                source.name,
                (
                    workflow_step
                    for workflow_step in workflow_steps
                    if workflow_step.id in step.depends_on
                ),
            ),
            values=(value for step_run in completed_steps for value in step_run.values),
        )

    @classmethod
    def _build_step_context(
        cls,
        *,
        layer_context: Context,
        step: WorkflowCandidateStep,
        workflow_steps: tuple[WorkflowCandidateStep, ...],
        completed_steps: list[WorkflowStepRun],
    ) -> Context:
        """Add resolved workflow inputs to a step-local context.

        Raises:
            WorkflowInputResolutionError: An input value reference has no
                committed value, or a context input has no matching event or
                field.
        """

        step_context = layer_context

        for binding in step.inputs:
            source = binding.source

            if isinstance(
                source,
                WorkflowConstantValue,
            ):
                step_context = step_context.append(
                    ContextEvent(
                        event_type=WORKFLOW_INPUT_BOUND_EVENT_TYPE,
                        payload={
                            "name": binding.name,
                            "value": source.value,
                            "constant": True,
                        },
                        producer="workflow-runner",
                    )
                )

                continue

            if isinstance(
                source,
                (
                    WorkflowValueReference,
                    WorkflowNamedValueReference,
                ),
            ):
                value = cls._resolve_input_value(
                    source=source,
                    step=step,
                    workflow_steps=workflow_steps,
                    completed_steps=completed_steps,
                )

                if value is None:
                    if isinstance(
                        source,
                        WorkflowValueReference,
                    ):
                        raise WorkflowInputResolutionError(
                            f"Workflow input {binding.name!r} could not resolve value "
                            f"{source.name!r} from step {source.producer_step_id}."
                        )

                    raise WorkflowInputResolutionError(
                        f"Workflow input {binding.name!r} could not resolve value "
                        f"{source.name!r} from any step it depends on."
                    )

                step_context = step_context.append(
                    ContextEvent(
                        event_type=WORKFLOW_INPUT_BOUND_EVENT_TYPE,
                        payload={
                            "name": binding.name,
                            "value": value.value,
                            "producer_step_id": str(
                                value.producer_step_id,
                            ),
                            "source_name": value.name,
                        },
                        producer="workflow-runner",
                    )
                )

                continue

            if not isinstance(
                source,
                WorkflowContextReference,
            ):
                raise RuntimeError("Workflow input binding contains an unsupported source type.")

            event = layer_context.latest(
                source.event_type,
            )

            if event is None:
                raise WorkflowInputResolutionError(
                    f"Workflow context input {binding.name!r} "
                    "could not resolve event type "
                    f"{source.event_type!r}."
                )

            if source.field_name not in event.payload:
                raise WorkflowInputResolutionError(
                    f"Workflow context input {binding.name!r} "
                    "could not resolve field "
                    f"{source.field_name!r} from event type "
                    f"{source.event_type!r}."
                )

            step_context = step_context.append(
                ContextEvent(
                    event_type=WORKFLOW_INPUT_BOUND_EVENT_TYPE,
                    payload={
                        "name": binding.name,
                        "value": event.payload[source.field_name],
                        "source_event_type": source.event_type,
                        "source_field_name": source.field_name,
                    },
                    producer="workflow-runner",
                )
            )

        return step_context

    @staticmethod
    def _input_resolution_failure(
        *,
        step: WorkflowCandidateStep,
        error: WorkflowInputResolutionError,
    ) -> _LayerStepResult:
        """Return the failed layer result of a step whose input did not resolve.

        The step records exactly one failed attempt carrying the resolution
        error, and its strategy is never executed.
        """

        resolved_at = datetime.now(
            tz=UTC,
        )

        return _LayerStepResult(
            step=step,
            status=WorkflowStepStatus.FAILED,
            attempts=(
                WorkflowStepAttempt(
                    attempt_number=1,
                    started_at=resolved_at,
                    completed_at=resolved_at,
                    failure=WorkflowStepFailure(
                        exception_type=type(error).__name__,
                        message=str(error),
                    ),
                ),
            ),
            error=error,
        )

    async def _execute_with_retry(
        self,
        *,
        strategy: Strategy,
        context: Context,
        retry_policy: WorkflowRetryPolicy,
        outputs: tuple[WorkflowValueBinding, ...] = (),
        step_id: UUID | None = None,
        confidence: str | None = None,
        lineage: RunLineage | None = None,
        layer_index: int = 0,
        journal: RunJournalWriter | None = None,
        prior_attempts: tuple[WorkflowStepAttempt, ...] = (),
    ) -> tuple[
        ExecutionResult | None,
        tuple[WorkflowStepAttempt, ...],
        Exception | None,
    ]:
        """Execute a strategy according to its retry policy.

        Before each retry, the runner waits the delay the policy assigns to
        that attempt. A zero delay retries immediately.

        An attempt succeeds only when every declared output binding resolves
        against its output. A binding that does not resolve fails the attempt
        with its `WorkflowValueResolutionError`, so it is retried like any
        other failure: a model may produce the declared shape on a later
        attempt.

        A step that declares a confidence also requires it to be a number
        from 0 to 1; anything else fails the attempt with its
        `WorkflowStepConfidenceError`, and is retried the same way (ADR 0098).

        With a run's lineage and a step, each attempt executes with that
        attempt's lineage current (ADR 0104).

        With a journal and a step, each attempt's start and finish are
        recorded outside the attempt, so an entry that cannot be recorded
        stops the run instead of failing the attempt (ADR 0105).

        A resumed step passes the attempts its journal recorded. One whose
        last recorded attempt succeeded is not executed again; one whose
        recorded attempts failed continues from the next attempt number,
        after that attempt's delay, and fails as recorded once none remain.
        """

        if confidence is not None and step_id is None:
            raise ValueError("A step that declares a confidence must name its step.")

        attempts: list[WorkflowStepAttempt] = list(prior_attempts)

        if prior_attempts:
            last = prior_attempts[-1]

            if last.execution is not None:
                return (
                    last.execution,
                    prior_attempts,
                    None,
                )

            if len(prior_attempts) >= retry_policy.max_attempts:
                return (
                    None,
                    prior_attempts,
                    RecordedStepFailure(last),
                )

            delay = retry_policy.delay_for_attempt(
                len(prior_attempts) + 1,
            )

            if delay > 0:
                await self._sleep(delay)

        for attempt_number in range(
            len(prior_attempts) + 1,
            retry_policy.max_attempts + 1,
        ):
            started_at = datetime.now(
                tz=UTC,
            )

            if journal is not None and step_id is not None:
                journal.record(
                    JournalAttemptStarted(
                        step_id=step_id,
                        layer_index=layer_index,
                        attempt_number=attempt_number,
                        started_at=started_at,
                    )
                )

            execution: ExecutionResult | None = None
            error: Exception | None = None

            try:
                if lineage is not None and step_id is not None:
                    with running_step(lineage.step(step_id=step_id, attempt=attempt_number)):
                        execution = await self._executor.execute(
                            strategy,
                            context,
                        )
                else:
                    execution = await self._executor.execute(
                        strategy,
                        context,
                    )

                for binding in outputs:
                    binding.resolve(execution.output)

                if step_id is not None:
                    self._resolve_confidence(
                        step_id=step_id,
                        confidence=confidence,
                        outputs=outputs,
                        output=execution.output,
                    )

            except Exception as caught:
                error = caught

            completed_at = datetime.now(
                tz=UTC,
            )

            if error is None:
                attempt = WorkflowStepAttempt(
                    attempt_number=attempt_number,
                    started_at=started_at,
                    completed_at=completed_at,
                    execution=execution,
                )
            else:
                attempt = WorkflowStepAttempt(
                    attempt_number=attempt_number,
                    started_at=started_at,
                    completed_at=completed_at,
                    failure=WorkflowStepFailure(
                        exception_type=type(error).__name__,
                        message=str(error),
                    ),
                )

            attempts.append(attempt)

            if journal is not None and step_id is not None:
                journal.record(
                    JournalAttemptFinished(
                        step_id=step_id,
                        layer_index=layer_index,
                        attempt=attempt,
                    )
                )

            if error is None:
                return (
                    execution,
                    tuple(attempts),
                    None,
                )

            if attempt_number == retry_policy.max_attempts:
                return (
                    None,
                    tuple(attempts),
                    error,
                )

            delay = retry_policy.delay_for_attempt(
                attempt_number + 1,
            )

            if delay > 0:
                await self._sleep(delay)

        raise AssertionError("Workflow retry execution completed without producing an outcome.")

    async def _execute_observed_step(
        self,
        *,
        step: WorkflowCandidateStep,
        step_context: Context,
        layer_index: int,
        lineage: RunLineage | None = None,
        journal: RunJournalWriter | None = None,
        prior_attempts: tuple[WorkflowStepAttempt, ...] = (),
    ) -> _StepOutcome:
        """Execute one eligible step to retry exhaustion, reporting its progress live."""

        self._notify(
            WorkflowStepStarted(
                step=step,
                layer_index=layer_index,
            )
        )

        execution, attempts, error = await self._execute_with_retry(
            strategy=step.strategy,
            context=step_context,
            retry_policy=step.retry_policy,
            outputs=step.outputs,
            step_id=step.id,
            confidence=step.confidence,
            lineage=lineage,
            layer_index=layer_index,
            journal=journal,
            prior_attempts=prior_attempts,
        )

        if execution is None:
            self._notify(
                WorkflowStepFinished(
                    step=step,
                    layer_index=layer_index,
                    status=WorkflowStepStatus.FAILED,
                    failure=attempts[-1].failure,
                    attempts=attempts,
                )
            )
        else:
            self._notify(
                WorkflowStepFinished(
                    step=step,
                    layer_index=layer_index,
                    status=WorkflowStepStatus.EXECUTED,
                    values=self._resolve_values(
                        step=step,
                        execution=execution,
                    ),
                    confidence=self._resolve_confidence(
                        step_id=step.id,
                        confidence=step.confidence,
                        outputs=step.outputs,
                        output=execution.output,
                    ),
                    attempts=attempts,
                    execution=execution,
                )
            )

        return _StepOutcome(
            execution=execution,
            attempts=attempts,
            error=error,
        )

    async def _execute_layer(
        self,
        eligible: tuple[tuple[WorkflowCandidateStep, Context], ...],
        *,
        layer_index: int = 0,
        lineage: RunLineage | None = None,
        journal: RunJournalWriter | None = None,
        prior_attempts: Mapping[UUID, tuple[WorkflowStepAttempt, ...]] | None = None,
    ) -> tuple[_StepOutcome, ...]:
        """Execute eligible layer steps concurrently, returning outcomes in order.

        Every step runs to retry exhaustion. Step failures are captured as
        outcomes rather than raised, so one failing step never cancels its
        siblings. Each step reports its start and finish as they happen.

        Raises:
            RunJournalError: An entry of the run's journal could not be
                recorded. The layer's other steps are cancelled.
        """

        try:
            async with asyncio.TaskGroup() as group:
                tasks = tuple(
                    group.create_task(
                        self._execute_observed_step(
                            step=step,
                            step_context=step_context,
                            layer_index=layer_index,
                            lineage=lineage,
                            journal=journal,
                            prior_attempts=(
                                () if prior_attempts is None else prior_attempts.get(step.id, ())
                            ),
                        )
                    )
                    for step, step_context in eligible
                )
        except BaseExceptionGroup as group_error:
            raise _first_exception(group_error) from None

        return tuple(task.result() for task in tasks)

    @staticmethod
    def _merge_execution_context(
        *,
        current_context: Context,
        execution_context: Context,
        execution: ExecutionResult,
        confidence: float | None = None,
    ) -> Context:
        """Append only events produced during strategy execution.

        A step that reports a confidence records it on every event it adds
        to the workflow's context (ADR 0098).
        """

        if execution.initial_context != execution_context:
            raise RuntimeError(
                "Workflow step execution did not preserve the expected step-start context."
            )

        initial_event_count = len(execution_context.events)

        produced_events = execution.final_context.events[initial_event_count:]

        merged = current_context

        for event in produced_events:
            merged = merged.append(
                event
                if confidence is None
                else event.model_copy(
                    update={"confidence": confidence},
                )
            )

        return merged

    async def run(
        self,
        workflow: WorkflowCandidate,
        context: Context,
        *,
        invocation_id: UUID | None = None,
    ) -> WorkflowRun:
        """Execute a workflow candidate and propagate FAIL_WORKFLOW failures.

        A run that executes a production invocation names it, and its
        journal records it on every entry.
        """

        result = await self._run(
            workflow=workflow,
            context=context,
            invocation_id=invocation_id,
        )

        if result.error is not None:
            raise result.error

        return result.run

    async def run_recording_failures(
        self,
        workflow: WorkflowCandidate,
        context: Context,
        *,
        invocation_id: UUID | None = None,
    ) -> WorkflowRun:
        """Execute a workflow candidate and return completed failure evidence.

        A run that executes a production invocation names it, and its
        journal records it on every entry.
        """

        result = await self._run(
            workflow=workflow,
            context=context,
            invocation_id=invocation_id,
        )

        return result.run

    async def resume(
        self,
        workflow: WorkflowCandidate,
        *,
        run_id: UUID,
        invocation_id: UUID | None = None,
    ) -> WorkflowRun:
        """Resume an unfinished run from its journal, and return completed failure evidence.

        The run keeps its ID, its initial context, its start and the
        invocation it executes. Its committed layers are reused, the layer it
        was executing reuses the attempts its steps finished, and an attempt
        that never finished is executed again under the same number. The
        journal records `run.resumed`, then continues where it stopped.

        A run whose journal already records its finish is rebuilt from the
        journal and returned as it finished; nothing executes.

        With leases, the run's lease is acquired first, and the journal is
        read again once it is held, so two processes never resume one run.

        A resume on behalf of a production invocation names it, and the run
        must be the one its journal records for it.

        Raises:
            RunLeaseHeldError: Another process holds the run's live lease.
            RunResumeError: The run cannot be resumed with this workflow.
            RunJournalError: An entry could not be recorded, or the lease was
                lost. The run stops there.
        """

        if self._journal is None:
            raise ValueError("A runner resumes only the runs it journals.")

        entries = self._journal.entries(run_id)

        _require_invocation(entries, run_id=run_id, invocation_id=invocation_id)

        finished = finished_run(entries)

        if finished is not None:
            return finished

        keeper = (
            RunLeaseKeeper(self._leases, run_id, policy=self._lease_policy)
            if self._leases is not None
            else None
        )

        if keeper is not None:
            keeper.acquire()

        try:
            entries = self._journal.entries(run_id)
            finished = finished_run(entries)

            if finished is not None:
                return finished

            point = resume_point(entries, run_id=run_id, workflow=workflow)

            lineage = run_lineage(
                point.initial_context,
                workflow_id=workflow.metadata.id,
                run_id=run_id,
            )

            journal = RunJournalWriter(
                self._journal,
                run_id=run_id,
                workflow_id=workflow.metadata.id,
                invocation_id=point.invocation_id,
                next_position=point.next_position,
                fence=keeper.check if keeper is not None else None,
            )

            if keeper is not None:
                keeper.start()

            result = await self._execute_run(
                workflow=workflow,
                context=point.initial_context,
                run_id=run_id,
                lineage=lineage,
                journal=journal,
                resume=point,
            )

            return result.run
        finally:
            if keeper is not None:
                keeper.stop()

                with contextlib.suppress(Exception):
                    keeper.release()

    async def _run(
        self,
        *,
        workflow: WorkflowCandidate,
        context: Context,
        invocation_id: UUID | None = None,
    ) -> _WorkflowExecutionResult:
        """Execute a workflow candidate while preserving terminal failure evidence.

        Raises:
            LineageError: The initial context records lineage that is not
                valid lineage. Nothing has run, and nothing is journaled.
            RunJournalError: An entry of the run's journal could not be
                recorded, or the run's lease was lost. The run stops there.
        """

        run_id = uuid4()
        lineage = run_lineage(
            context,
            workflow_id=workflow.metadata.id,
            run_id=run_id,
        )

        keeper = (
            RunLeaseKeeper(self._leases, run_id, policy=self._lease_policy)
            if self._leases is not None
            else None
        )

        journal = (
            RunJournalWriter(
                self._journal,
                run_id=run_id,
                workflow_id=workflow.metadata.id,
                invocation_id=invocation_id,
                fence=keeper.check if keeper is not None else None,
            )
            if self._journal is not None
            else None
        )

        parent = lineage_of(context)

        if self._children is not None and parent is not None:
            self._children.record(
                RunChild.of(
                    parent,
                    run_id=run_id,
                    workflow_id=workflow.metadata.id,
                    invocation_id=invocation_id,
                    recorded_at=datetime.now(tz=UTC),
                )
            )

        if keeper is None:
            return await self._execute_run(
                workflow=workflow,
                context=context,
                run_id=run_id,
                lineage=lineage,
                journal=journal,
            )

        keeper.acquire()
        keeper.start()

        try:
            return await self._execute_run(
                workflow=workflow,
                context=context,
                run_id=run_id,
                lineage=lineage,
                journal=journal,
            )
        finally:
            keeper.stop()

            with contextlib.suppress(Exception):
                keeper.release()

    async def _execute_run(
        self,
        *,
        workflow: WorkflowCandidate,
        context: Context,
        run_id: UUID,
        lineage: RunLineage,
        journal: RunJournalWriter | None,
        resume: RunResumePoint | None = None,
    ) -> _WorkflowExecutionResult:
        """Execute the run's layers in order, journaling them if there is a journal.

        A resumed run starts from its resume point: its committed layers are
        kept, and the first layer it did not commit reuses the attempts its
        steps finished.
        """

        if resume is None:
            started_at = datetime.now(
                tz=UTC,
            )

            if journal is not None:
                journal.record(
                    JournalRunStarted(
                        workflow=workflow.metadata,
                        workflow_revision=workflow.revision,
                        initial_context=context,
                        started_at=started_at,
                    )
                )

            current_context = context
            completed_steps: list[WorkflowStepRun] = []
            blocked_step_ids: set[UUID] = set()
            first_layer = 0
            prior_attempts: Mapping[UUID, tuple[WorkflowStepAttempt, ...]] = {}
            halted = False
            halting_step_id: UUID | None = None
        else:
            if journal is not None:
                journal.record(JournalRunResumed(resumed_at=datetime.now(tz=UTC)))

            started_at = resume.started_at
            current_context = resume.context
            completed_steps = list(resume.steps)
            blocked_step_ids = set(resume.blocked_step_ids)
            first_layer = resume.next_layer
            prior_attempts = resume.attempts
            halted = resume.halting_step_id is not None
            halting_step_id = resume.halting_step_id

        terminal_error: Exception | None = None

        for layer_index, layer in enumerate(workflow.execution_layers()):
            if halted or layer_index < first_layer:
                continue

            layer_prior = prior_attempts if layer_index == first_layer else {}
            layer_context = current_context
            committed_count = len(completed_steps)
            layer_results: list[_LayerStepResult] = []
            eligible: list[tuple[WorkflowCandidateStep, Context]] = []

            for step in layer:
                #
                # A dependency skipped because of SKIP_DEPENDENTS
                # blocks this step transitively.
                #
                if any(dependency_id in blocked_step_ids for dependency_id in step.depends_on):
                    blocked_step_ids.add(step.id)

                    layer_results.append(
                        _LayerStepResult(
                            step=step,
                            status=WorkflowStepStatus.SKIPPED,
                        )
                    )

                    self._notify(
                        WorkflowStepFinished(
                            step=step,
                            layer_index=layer_index,
                            status=WorkflowStepStatus.SKIPPED,
                        )
                    )

                    continue

                #
                # Normal conditional eligibility.
                #
                if not self._conditions_are_satisfied(
                    step=step,
                    completed_steps=completed_steps,
                ):
                    layer_results.append(
                        _LayerStepResult(
                            step=step,
                            status=WorkflowStepStatus.SKIPPED,
                        )
                    )

                    self._notify(
                        WorkflowStepFinished(
                            step=step,
                            layer_index=layer_index,
                            status=WorkflowStepStatus.SKIPPED,
                        )
                    )

                    continue

                #
                # A resumed step whose recorded attempt succeeded reuses it,
                # with the very context that attempt executed in.
                #
                recorded = layer_prior.get(step.id, ())

                if recorded and recorded[-1].execution is not None:
                    eligible.append(
                        (
                            step,
                            recorded[-1].execution.initial_context,
                        )
                    )

                    continue

                #
                # An input without a value fails the step under its own
                # policy. Resolution is deterministic, so it is never retried.
                #
                try:
                    step_context = self._build_step_context(
                        layer_context=layer_context,
                        step=step,
                        workflow_steps=workflow.steps,
                        completed_steps=completed_steps,
                    )
                except WorkflowInputResolutionError as error:
                    failure = self._input_resolution_failure(
                        step=step,
                        error=error,
                    )

                    layer_results.append(failure)

                    self._notify(
                        WorkflowStepFinished(
                            step=step,
                            layer_index=layer_index,
                            status=WorkflowStepStatus.FAILED,
                            failure=failure.attempts[-1].failure,
                            attempts=failure.attempts,
                        )
                    )

                    continue

                eligible.append(
                    (
                        step,
                        step_context,
                    )
                )

            #
            # Execute every eligible step of the layer concurrently.
            #
            outcomes = await self._execute_layer(
                tuple(eligible),
                layer_index=layer_index,
                lineage=lineage,
                journal=journal,
                prior_attempts=layer_prior,
            )

            for (step, step_context), outcome in zip(
                eligible,
                outcomes,
                strict=True,
            ):
                if outcome.error is not None:
                    layer_results.append(
                        _LayerStepResult(
                            step=step,
                            status=WorkflowStepStatus.FAILED,
                            step_context=step_context,
                            attempts=outcome.attempts,
                            error=outcome.error,
                        )
                    )

                    continue

                if outcome.execution is None:
                    raise RuntimeError(
                        "Successful workflow step execution did not produce an execution result."
                    )

                layer_results.append(
                    _LayerStepResult(
                        step=step,
                        status=WorkflowStepStatus.EXECUTED,
                        step_context=step_context,
                        execution=outcome.execution,
                        attempts=outcome.attempts,
                    )
                )

            #
            # Commit the layer in declared workflow order. Output bindings
            # already resolved during the successful attempt. The first
            # FAIL_WORKFLOW failure in declared order stops the run once the
            # whole layer is recorded.
            #
            declared_order = {step.id: index for index, step in enumerate(layer)}

            layer_results.sort(
                key=lambda result: declared_order[result.step.id],
            )

            for result in layer_results:
                step = result.step

                if result.status is WorkflowStepStatus.SKIPPED:
                    completed_steps.append(
                        WorkflowStepRun(
                            step_id=step.id,
                            layer_index=layer_index,
                            status=WorkflowStepStatus.SKIPPED,
                            execution=None,
                            attempts=(),
                            values=(),
                        )
                    )

                    continue

                if result.status is WorkflowStepStatus.FAILED:
                    if result.error is None:
                        raise RuntimeError("Failed workflow step is missing its failure.")

                    completed_steps.append(
                        WorkflowStepRun(
                            step_id=step.id,
                            layer_index=layer_index,
                            status=WorkflowStepStatus.FAILED,
                            execution=None,
                            attempts=result.attempts,
                            values=(),
                        )
                    )

                    if step.failure_policy is WorkflowFailurePolicy.FAIL_WORKFLOW:
                        if terminal_error is None:
                            terminal_error = result.error
                            halting_step_id = step.id

                    elif step.failure_policy is WorkflowFailurePolicy.SKIP_DEPENDENTS:
                        blocked_step_ids.add(step.id)

                    continue

                execution = result.execution

                if execution is None:
                    raise RuntimeError("Executed workflow step is missing its execution result.")

                if result.step_context is None:
                    raise RuntimeError("Executed workflow step is missing its execution context.")

                confidence = self._resolve_confidence(
                    step_id=step.id,
                    confidence=step.confidence,
                    outputs=step.outputs,
                    output=execution.output,
                )

                current_context = self._merge_execution_context(
                    current_context=current_context,
                    execution_context=result.step_context,
                    execution=execution,
                    confidence=confidence,
                )

                values = self._resolve_values(
                    step=step,
                    execution=execution,
                )

                completed_steps.append(
                    WorkflowStepRun(
                        step_id=step.id,
                        layer_index=layer_index,
                        status=WorkflowStepStatus.EXECUTED,
                        execution=execution,
                        attempts=result.attempts,
                        values=values,
                        confidence=confidence,
                    )
                )

            if journal is not None:
                journal.record(
                    JournalLayerCommitted(
                        layer_index=layer_index,
                        steps=tuple(completed_steps[committed_count:]),
                        events=current_context.events[len(layer_context.events) :],
                        blocked_step_ids=tuple(
                            step.id for step in workflow.steps if step.id in blocked_step_ids
                        ),
                    )
                )

            if terminal_error is not None:
                break

        completed_at = datetime.now(
            tz=UTC,
        )

        if journal is not None:
            journal.record(
                JournalRunFinished(
                    completed_at=completed_at,
                    halted=halted or terminal_error is not None,
                    halting_step_id=halting_step_id,
                )
            )

        run = WorkflowRun(
            id=run_id,
            workflow=workflow.metadata,
            workflow_revision=workflow.revision,
            steps=tuple(completed_steps),
            initial_context=context,
            final_context=current_context,
            started_at=started_at,
            completed_at=completed_at,
            halted=halted or terminal_error is not None,
            halting_step_id=halting_step_id,
        )

        return _WorkflowExecutionResult(
            run=run,
            error=terminal_error,
        )


__all__ = [
    "RecordedStepFailure",
    "RetrySleep",
    "WorkflowRunner",
]

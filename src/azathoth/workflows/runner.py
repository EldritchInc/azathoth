"""Workflow execution orchestration."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import Context, ContextEvent
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


class WorkflowRunner:
    """Execute workflow candidates.

    The eligible steps of each dependency layer execute concurrently. A layer
    commits only after every one of its steps has finished, always in declared
    order, so the recorded run and its final context are identical whatever
    order the steps finish in.

    An optional observer is told live when each step starts and finishes, in
    the order that actually happens. It only watches: the recorded run is the
    same with or without it.
    """

    def __init__(
        self,
        *,
        executor: StrategyExecutor | None = None,
        sleep: RetrySleep | None = None,
        observer: WorkflowRunObserver | None = None,
    ) -> None:
        self._executor = executor if executor is not None else StrategyExecutor()
        self._sleep: RetrySleep = sleep if sleep is not None else _sleep
        self._observer = observer

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
        """

        if confidence is not None and step_id is None:
            raise ValueError("A step that declares a confidence must name its step.")

        attempts: list[WorkflowStepAttempt] = []

        for attempt_number in range(
            1,
            retry_policy.max_attempts + 1,
        ):
            started_at = datetime.now(
                tz=UTC,
            )

            try:
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

                completed_at = datetime.now(
                    tz=UTC,
                )

                attempts.append(
                    WorkflowStepAttempt(
                        attempt_number=attempt_number,
                        started_at=started_at,
                        completed_at=completed_at,
                        execution=execution,
                    )
                )

                return (
                    execution,
                    tuple(attempts),
                    None,
                )

            except Exception as error:
                completed_at = datetime.now(
                    tz=UTC,
                )

                attempts.append(
                    WorkflowStepAttempt(
                        attempt_number=attempt_number,
                        started_at=started_at,
                        completed_at=completed_at,
                        failure=WorkflowStepFailure(
                            exception_type=type(error).__name__,
                            message=str(error),
                        ),
                    )
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
        )

        if execution is None:
            self._notify(
                WorkflowStepFinished(
                    step=step,
                    layer_index=layer_index,
                    status=WorkflowStepStatus.FAILED,
                    failure=attempts[-1].failure,
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
    ) -> tuple[_StepOutcome, ...]:
        """Execute eligible layer steps concurrently, returning outcomes in order.

        Every step runs to retry exhaustion. Step failures are captured as
        outcomes rather than raised, so one failing step never cancels its
        siblings. Each step reports its start and finish as they happen.
        """

        async with asyncio.TaskGroup() as group:
            tasks = tuple(
                group.create_task(
                    self._execute_observed_step(
                        step=step,
                        step_context=step_context,
                        layer_index=layer_index,
                    )
                )
                for step, step_context in eligible
            )

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
    ) -> WorkflowRun:
        """Execute a workflow candidate and propagate FAIL_WORKFLOW failures."""

        result = await self._run(
            workflow=workflow,
            context=context,
        )

        if result.error is not None:
            raise result.error

        return result.run

    async def run_recording_failures(
        self,
        workflow: WorkflowCandidate,
        context: Context,
    ) -> WorkflowRun:
        """Execute a workflow candidate and return completed failure evidence."""

        result = await self._run(
            workflow=workflow,
            context=context,
        )

        return result.run

    async def _run(
        self,
        *,
        workflow: WorkflowCandidate,
        context: Context,
    ) -> _WorkflowExecutionResult:
        """Execute a workflow candidate while preserving terminal failure evidence."""

        started_at = datetime.now(
            tz=UTC,
        )

        current_context = context
        completed_steps: list[WorkflowStepRun] = []
        blocked_step_ids: set[UUID] = set()
        terminal_error: Exception | None = None
        halting_step_id: UUID | None = None

        for layer_index, layer in enumerate(workflow.execution_layers()):
            layer_context = current_context
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

            if terminal_error is not None:
                break

        completed_at = datetime.now(
            tz=UTC,
        )

        run = WorkflowRun(
            workflow=workflow.metadata,
            workflow_revision=workflow.revision,
            steps=tuple(completed_steps),
            initial_context=context,
            final_context=current_context,
            started_at=started_at,
            completed_at=completed_at,
            halted=terminal_error is not None,
            halting_step_id=halting_step_id,
        )

        return _WorkflowExecutionResult(
            run=run,
            error=terminal_error,
        )

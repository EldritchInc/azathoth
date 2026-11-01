"""Tracing workflow runs and their steps (ADR 0100).

A run is one `azathoth.run` span. Each step is an `azathoth.step` span under
it, started and ended live, as the runner reports the step starting and
finishing. A skipped step, which never starts, is a span of no duration.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context
from azathoth.execution import StrategyExecutor
from azathoth.telemetry.api import Telemetry, TelemetrySpan
from azathoth.telemetry.attributes import run_attributes, step_attributes
from azathoth.telemetry.conventions import (
    ATTEMPT_FAILED_EVENT,
    ATTEMPT_NUMBER,
    ERROR_TYPE,
    RUN_SPAN,
    STEP_SPAN,
    WORKFLOW_ID,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunner,
    WorkflowRunObserver,
    WorkflowStepFinished,
    WorkflowStepStarted,
    WorkflowStepStatus,
    combine_observers,
)
from azathoth.workflows.runner import RetrySleep

RUN_FAILED_ERROR_TYPE = "WorkflowRunFailed"
"""The error type of a run that failed without a step failure to name."""


@dataclass
class _ActiveStep:
    """A step span, and the token restoring the context it replaced."""

    span: TelemetrySpan
    token: object


class TracingRunObserver:
    """Start and end one step span per step, under one run span.

    The runner reports a step starting and finishing from the task that runs
    it, so the step's span is current for exactly that step's work: a
    process tool it runs sees that step's trace context (ADR 0100).
    """

    def __init__(
        self,
        telemetry: Telemetry,
        run_span: TelemetrySpan,
    ) -> None:
        self._telemetry = telemetry
        self._run_span = run_span
        self._active: dict[UUID, _ActiveStep] = {}

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Start a step's span when it starts, and finish it when it finishes."""

        if isinstance(event, WorkflowStepStarted):
            self._start(event)
        else:
            self._finish(event)

    def _start(
        self,
        event: WorkflowStepStarted,
    ) -> None:
        """Start one step's span and make it current."""

        span = self._telemetry.start_span(STEP_SPAN, parent=self._run_span)

        self._active[event.step.id] = _ActiveStep(
            span=span,
            token=self._telemetry.activate(span),
        )

    def _finish(
        self,
        event: WorkflowStepFinished,
    ) -> None:
        """Describe one step's span and end it."""

        active = self._active.pop(event.step.id, None)

        if active is None:
            span = self._telemetry.start_span(STEP_SPAN, parent=self._run_span)
        else:
            span = active.span
            self._telemetry.deactivate(active.token)

        execution = event.execution

        span.set_attributes(
            step_attributes(
                event.step.id,
                event.status,
                attempts=len(event.attempts),
                strategy_name=(
                    execution.strategy_name
                    if execution is not None
                    else event.step.strategy.metadata.name
                ),
                confidence=event.confidence,
                metrics=execution.metrics if execution is not None else None,
            )
        )

        for attempt in event.attempts:
            if attempt.failure is not None:
                span.add_event(
                    ATTEMPT_FAILED_EVENT,
                    {
                        ATTEMPT_NUMBER: attempt.attempt_number,
                        ERROR_TYPE: attempt.failure.exception_type,
                    },
                    timestamp=attempt.completed_at,
                )

        if event.status is WorkflowStepStatus.FAILED and event.failure is not None:
            span.set_error(event.failure.exception_type)

        span.end()


@dataclass
class RunTrace:
    """The span of one run, and the observer that traces its steps."""

    span: TelemetrySpan
    observer: TracingRunObserver
    recorded: list[WorkflowRun] = field(default_factory=list)

    def record(
        self,
        run: WorkflowRun,
    ) -> None:
        """Describe the run span with the run's recorded identity and outcome.

        A failed run names the type of the failure that halted it.
        """

        self.recorded.append(run)
        self.span.set_attributes(run_attributes(run))

        if run.succeeded:
            return

        self.span.set_error(_halting_error_type(run))


def _halting_error_type(
    run: WorkflowRun,
) -> str:
    """Return the exception type of the failure that halted one run."""

    for step in run.steps:
        if run.halting_step_id is not None and step.step_id != run.halting_step_id:
            continue

        if step.status is WorkflowStepStatus.FAILED and step.attempts:
            failure = step.attempts[-1].failure

            if failure is not None:
                return failure.exception_type

    return RUN_FAILED_ERROR_TYPE


@contextmanager
def traced_run(
    telemetry: Telemetry,
    *,
    workflow_id: UUID,
) -> Iterator[RunTrace]:
    """Run a block inside one current run span, with an observer for its steps.

    Pass the trace's observer to the runner, and the finished run to
    `record`. An exception escaping the block marks the span failed with its
    type, and is raised again.
    """

    span = telemetry.start_span(
        RUN_SPAN,
        {WORKFLOW_ID: str(workflow_id)},
        start_time=datetime.now(UTC),
    )
    token = telemetry.activate(span)

    try:
        yield RunTrace(
            span=span,
            observer=TracingRunObserver(telemetry, span),
        )
    except BaseException as exc:
        span.set_error(type(exc).__name__)

        raise
    finally:
        telemetry.deactivate(token)
        span.end()


class TracingWorkflowRunner(WorkflowRunner):
    """A workflow runner that traces every run it executes, and its steps.

    Each run is executed by a plain runner with the same executor and retry
    sleep, observed by both this runner's own observer and the run's
    tracing observer, so concurrent runs never share a trace.
    """

    def __init__(
        self,
        telemetry: Telemetry,
        *,
        executor: StrategyExecutor | None = None,
        sleep: RetrySleep | None = None,
        observer: WorkflowRunObserver | None = None,
    ) -> None:
        super().__init__(
            executor=executor,
            sleep=sleep,
            observer=observer,
        )

        self._telemetry = telemetry

    def _traced_runner(
        self,
        trace: RunTrace,
    ) -> WorkflowRunner:
        """Return the plain runner that executes one traced run."""

        return WorkflowRunner(
            executor=self._executor,
            sleep=self._sleep,
            observer=combine_observers(trace.observer, self._observer),
        )

    async def run(
        self,
        workflow: WorkflowCandidate,
        context: Context,
    ) -> WorkflowRun:
        """Execute and trace a workflow candidate, propagating FAIL_WORKFLOW failures.

        A failure that escapes marks the run span failed with its type.
        """

        with traced_run(self._telemetry, workflow_id=workflow.metadata.id) as trace:
            run = await self._traced_runner(trace).run(workflow, context)

            trace.record(run)

        return run

    async def run_recording_failures(
        self,
        workflow: WorkflowCandidate,
        context: Context,
    ) -> WorkflowRun:
        """Execute and trace a workflow candidate, returning completed failure evidence."""

        with traced_run(self._telemetry, workflow_id=workflow.metadata.id) as trace:
            run = await self._traced_runner(trace).run_recording_failures(workflow, context)

            trace.record(run)

        return run


def tracing_runner(
    telemetry: Telemetry,
    *,
    observer: WorkflowRunObserver | None = None,
) -> WorkflowRunner:
    """Return a runner that traces its runs when telemetry is on, and a plain one otherwise."""

    if not telemetry.enabled:
        return WorkflowRunner(observer=observer)

    return TracingWorkflowRunner(telemetry, observer=observer)


__all__ = [
    "RUN_FAILED_ERROR_TYPE",
    "RunTrace",
    "TracingRunObserver",
    "TracingWorkflowRunner",
    "traced_run",
    "tracing_runner",
]

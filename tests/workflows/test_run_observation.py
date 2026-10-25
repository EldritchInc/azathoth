"""Tests for live observation of workflow step progress."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import Strategy
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowContextReference,
    WorkflowFailurePolicy,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunner,
    WorkflowStepFinished,
    WorkflowStepStarted,
    WorkflowStepStatus,
    WorkflowValueBinding,
)
from tests.workflows.test_input_resolution_failures import (
    NamedStrategy,
)

WORKFLOW_ID = UUID("c3000000-0000-4000-8000-000000000001")

FIRST_STEP_ID = UUID("c3000000-0000-4000-8000-000000000011")
SECOND_STEP_ID = UUID("c3000000-0000-4000-8000-000000000012")
THIRD_STEP_ID = UUID("c3000000-0000-4000-8000-000000000013")

FIRST_STRATEGY_ID = UUID("c3000000-0000-4000-8000-000000000021")
SECOND_STRATEGY_ID = UUID("c3000000-0000-4000-8000-000000000022")
THIRD_STRATEGY_ID = UUID("c3000000-0000-4000-8000-000000000023")

RENDEZVOUS_TIMEOUT_SECONDS = 1.0

NO_FAILURES: frozenset[str] = frozenset()

COUNT_OUTPUT = (
    WorkflowValueBinding(
        name="count",
        path=("count",),
    ),
)

EXECUTION_TIME = datetime(
    2026,
    10,
    25,
    16,
    0,
    tzinfo=UTC,
)

EventSummary = tuple[str, str, WorkflowStepStatus | None]
"""An event kind, the strategy name of its step, and its finished status."""


class RecordingObserver:
    """Record every observed event."""

    def __init__(self) -> None:
        self.events: list[WorkflowRunEvent] = []

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Record one event."""

        self.events.append(event)


class RaisingObserver:
    """Raise on every observed event."""

    def __init__(self) -> None:
        self.calls = 0

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Fail the observation."""

        self.calls += 1

        raise RuntimeError("Observer exploded.")


class CountingExecutor(StrategyExecutor):
    """Answer each strategy with the length of its name, failing configured ones."""

    def __init__(
        self,
        *,
        failing: frozenset[str] = NO_FAILURES,
    ) -> None:
        self._failing = failing
        self.calls: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record the call, then answer or fail."""

        name = strategy.metadata.name
        self.calls.append(name)

        if name in self._failing:
            raise RuntimeError(f"{name} failed")

        output: JsonValue = {
            "count": len(name),
        }

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=name,
            strategy_version=strategy.metadata.version,
            output=output,
            initial_context=context,
            final_context=context,
            started_at=EXECUTION_TIME,
            completed_at=EXECUTION_TIME,
        )


class GatedExecutor(CountingExecutor):
    """Hold the `Slow` strategy until the observer has seen `Fast` finish.

    A runner that reported steps only after the layer finished, or that ran
    the layer's steps one at a time, would time out here.
    """

    def __init__(
        self,
        fast_finished: asyncio.Event,
    ) -> None:
        super().__init__()
        self._fast_finished = fast_finished

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Wait for `Fast` to be observed finishing before answering `Slow`."""

        if strategy.metadata.name == "Slow":
            await asyncio.wait_for(
                self._fast_finished.wait(),
                timeout=RENDEZVOUS_TIMEOUT_SECONDS,
            )

        return await super().execute(
            strategy,
            context,
        )


class GateOpeningObserver(RecordingObserver):
    """Record events, opening the gate once `Fast` is seen finishing."""

    def __init__(
        self,
        fast_finished: asyncio.Event,
    ) -> None:
        super().__init__()
        self._fast_finished = fast_finished

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        """Record one event and open the gate on `Fast` finishing."""

        super().observe(event)

        if (
            isinstance(
                event,
                WorkflowStepFinished,
            )
            and event.step.strategy.metadata.name == "Fast"
        ):
            self._fast_finished.set()


def create_step(
    *,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
    depends_on: tuple[UUID, ...] = (),
    inputs: tuple[WorkflowInputBinding, ...] = (),
    retry_policy: WorkflowRetryPolicy | None = None,
    failure_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.CONTINUE,
) -> WorkflowCandidateStep:
    """Create one counting step declaring a `count` output."""

    return WorkflowCandidateStep(
        id=step_id,
        strategy=NamedStrategy(
            strategy_id=strategy_id,
            name=name,
        ),
        depends_on=depends_on,
        inputs=inputs,
        outputs=COUNT_OUTPUT,
        retry_policy=retry_policy if retry_policy is not None else WorkflowRetryPolicy(),
        failure_policy=failure_policy,
    )


def create_candidate(
    *steps: WorkflowCandidateStep,
) -> WorkflowCandidate:
    """Create one candidate from the given steps."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Run observation",
            description="Exercise live step progress.",
            version="1.0.0",
        ),
        steps=steps,
    )


def create_chain(
    *,
    first_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.CONTINUE,
) -> WorkflowCandidate:
    """Create a `Counter` step followed by a dependent `Reporter` step."""

    return create_candidate(
        create_step(
            step_id=FIRST_STEP_ID,
            strategy_id=FIRST_STRATEGY_ID,
            name="Counter",
            failure_policy=first_policy,
        ),
        create_step(
            step_id=SECOND_STEP_ID,
            strategy_id=SECOND_STRATEGY_ID,
            name="Reporter",
            depends_on=(FIRST_STEP_ID,),
        ),
    )


def observe_run(
    candidate: WorkflowCandidate,
    *,
    executor: CountingExecutor,
    observer: RecordingObserver | None = None,
) -> tuple[WorkflowRun, list[WorkflowRunEvent]]:
    """Run one candidate under a recording observer."""

    recorder = observer if observer is not None else RecordingObserver()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
            observer=recorder,
        ).run_recording_failures(
            candidate,
            Context(),
        )
    )

    return run, recorder.events


def summarize(
    events: list[WorkflowRunEvent],
) -> list[EventSummary]:
    """Summarize events as their kind, step strategy name, and finished status."""

    summaries: list[EventSummary] = []

    for event in events:
        name = event.step.strategy.metadata.name

        if isinstance(
            event,
            WorkflowStepStarted,
        ):
            summaries.append(("started", name, None))
            continue

        summaries.append(("finished", name, event.status))

    return summaries


def require_finished(
    events: list[WorkflowRunEvent],
    name: str,
) -> WorkflowStepFinished:
    """Return the finished event of the named step."""

    finished = [
        event
        for event in events
        if isinstance(
            event,
            WorkflowStepFinished,
        )
        and event.step.strategy.metadata.name == name
    ]

    assert len(finished) == 1

    return finished[0]


def evidence(
    run: WorkflowRun,
) -> list[tuple[UUID, WorkflowStepStatus, int, JsonValue, tuple[tuple[str, JsonValue], ...]]]:
    """Return a run's recorded step evidence without timestamps."""

    return [
        (
            step.step_id,
            step.status,
            len(step.attempts),
            step.execution.output if step.execution is not None else None,
            tuple((value.name, value.value) for value in step.values),
        )
        for step in run.steps
    ]


def test_executed_steps_start_then_finish_with_their_values() -> None:
    run, events = observe_run(
        create_chain(),
        executor=CountingExecutor(),
    )

    assert run.succeeded
    assert summarize(events) == [
        ("started", "Counter", None),
        ("finished", "Counter", WorkflowStepStatus.EXECUTED),
        ("started", "Reporter", None),
        ("finished", "Reporter", WorkflowStepStatus.EXECUTED),
    ]

    counter = require_finished(events, "Counter")

    assert counter.layer_index == 0
    assert counter.failure is None
    assert tuple((value.name, value.value) for value in counter.values) == (("count", 7),)
    assert require_finished(events, "Reporter").layer_index == 1


def test_events_carry_the_candidate_step() -> None:
    candidate = create_chain()

    _run, events = observe_run(
        candidate,
        executor=CountingExecutor(),
    )

    assert events[0].step is candidate.steps[0]


def test_failed_step_finishes_with_its_failure_and_no_values() -> None:
    _run, events = observe_run(
        create_chain(),
        executor=CountingExecutor(
            failing=frozenset({"Counter"}),
        ),
    )

    counter = require_finished(events, "Counter")

    assert counter.status is WorkflowStepStatus.FAILED
    assert counter.values == ()
    assert counter.failure is not None
    assert counter.failure.exception_type == "RuntimeError"
    assert counter.failure.message == "Counter failed"


def test_retried_step_starts_once_and_finishes_once() -> None:
    executor = CountingExecutor(
        failing=frozenset({"Counter"}),
    )

    _run, events = observe_run(
        create_candidate(
            create_step(
                step_id=FIRST_STEP_ID,
                strategy_id=FIRST_STRATEGY_ID,
                name="Counter",
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=3,
                ),
            ),
        ),
        executor=executor,
    )

    assert executor.calls == ["Counter", "Counter", "Counter"]
    assert summarize(events) == [
        ("started", "Counter", None),
        ("finished", "Counter", WorkflowStepStatus.FAILED),
    ]


def test_skipped_step_finishes_without_starting() -> None:
    _run, events = observe_run(
        create_chain(
            first_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
        ),
        executor=CountingExecutor(
            failing=frozenset({"Counter"}),
        ),
    )

    assert summarize(events) == [
        ("started", "Counter", None),
        ("finished", "Counter", WorkflowStepStatus.FAILED),
        ("finished", "Reporter", WorkflowStepStatus.SKIPPED),
    ]

    reporter = require_finished(events, "Reporter")

    assert reporter.values == ()
    assert reporter.failure is None


def test_unresolved_input_finishes_failed_without_starting() -> None:
    _run, events = observe_run(
        create_candidate(
            create_step(
                step_id=FIRST_STEP_ID,
                strategy_id=FIRST_STRATEGY_ID,
                name="Reader",
                inputs=(
                    WorkflowInputBinding(
                        name="text",
                        source=WorkflowContextReference(
                            event_type="request.received",
                            field_name="input",
                        ),
                    ),
                ),
            ),
        ),
        executor=CountingExecutor(),
    )

    assert summarize(events) == [
        ("finished", "Reader", WorkflowStepStatus.FAILED),
    ]

    reader = require_finished(events, "Reader")

    assert reader.failure is not None
    assert reader.failure.message == (
        "Workflow context input 'text' could not resolve event type 'request.received'."
    )


def test_unresolvable_output_finishes_failed() -> None:
    _run, events = observe_run(
        create_candidate(
            WorkflowCandidateStep(
                id=FIRST_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=FIRST_STRATEGY_ID,
                    name="Counter",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="total",
                        path=("total",),
                    ),
                ),
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
        ),
        executor=CountingExecutor(),
    )

    counter = require_finished(events, "Counter")

    assert counter.status is WorkflowStepStatus.FAILED
    assert counter.failure is not None
    assert counter.failure.exception_type == "WorkflowValueResolutionError"


def test_events_arrive_live_in_completion_order() -> None:
    async def run_gated() -> list[WorkflowRunEvent]:
        fast_finished = asyncio.Event()

        observer = GateOpeningObserver(fast_finished)

        await WorkflowRunner(
            executor=GatedExecutor(fast_finished),
            observer=observer,
        ).run_recording_failures(
            create_candidate(
                create_step(
                    step_id=FIRST_STEP_ID,
                    strategy_id=FIRST_STRATEGY_ID,
                    name="Slow",
                ),
                create_step(
                    step_id=SECOND_STEP_ID,
                    strategy_id=SECOND_STRATEGY_ID,
                    name="Fast",
                ),
            ),
            Context(),
        )

        return observer.events

    events = asyncio.run(run_gated())

    assert summarize(events) == [
        ("started", "Slow", None),
        ("started", "Fast", None),
        ("finished", "Fast", WorkflowStepStatus.EXECUTED),
        ("finished", "Slow", WorkflowStepStatus.EXECUTED),
    ]


def test_observed_run_records_the_same_evidence_as_an_unobserved_run() -> None:
    unobserved = asyncio.run(
        WorkflowRunner(
            executor=CountingExecutor(
                failing=frozenset({"Counter"}),
            ),
        ).run_recording_failures(
            create_chain(),
            Context(),
        )
    )

    observed, _events = observe_run(
        create_chain(),
        executor=CountingExecutor(
            failing=frozenset({"Counter"}),
        ),
    )

    assert evidence(observed) == evidence(unobserved)


def test_raising_observer_never_changes_the_run() -> None:
    observer = RaisingObserver()

    run = asyncio.run(
        WorkflowRunner(
            executor=CountingExecutor(),
            observer=observer,
        ).run_recording_failures(
            create_chain(),
            Context(),
        )
    )

    unobserved = asyncio.run(
        WorkflowRunner(
            executor=CountingExecutor(),
        ).run_recording_failures(
            create_chain(),
            Context(),
        )
    )

    assert observer.calls == 4
    assert run.succeeded
    assert evidence(run) == evidence(unobserved)


def test_runner_without_observer_still_runs() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=CountingExecutor(),
        ).run_recording_failures(
            create_chain(),
            Context(),
        )
    )

    assert run.succeeded
    assert evidence(run)[0][4] == (("count", 7),)

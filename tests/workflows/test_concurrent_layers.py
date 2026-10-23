"""Tests for concurrent execution of workflow layers."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.context import Context, ContextEvent
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("5b0b6f1e-6a1f-4c55-9d8e-1f0a2b3c4d01")

LEFT_STEP_ID = UUID("5b0b6f1e-6a1f-4c55-9d8e-1f0a2b3c4d11")
RIGHT_STEP_ID = UUID("5b0b6f1e-6a1f-4c55-9d8e-1f0a2b3c4d12")
THIRD_STEP_ID = UUID("5b0b6f1e-6a1f-4c55-9d8e-1f0a2b3c4d13")
DOWNSTREAM_STEP_ID = UUID("5b0b6f1e-6a1f-4c55-9d8e-1f0a2b3c4d14")

LEFT_STRATEGY_ID = UUID("5b0b6f1e-6a1f-4c55-9d8e-1f0a2b3c4d21")
RIGHT_STRATEGY_ID = UUID("5b0b6f1e-6a1f-4c55-9d8e-1f0a2b3c4d22")
THIRD_STRATEGY_ID = UUID("5b0b6f1e-6a1f-4c55-9d8e-1f0a2b3c4d23")
DOWNSTREAM_STRATEGY_ID = UUID("5b0b6f1e-6a1f-4c55-9d8e-1f0a2b3c4d24")

RENDEZVOUS_TIMEOUT_SECONDS = 1.0

NO_FAILURES: frozenset[str] = frozenset()

EXECUTION_TIME = datetime(
    2026,
    10,
    23,
    12,
    0,
    tzinfo=UTC,
)


class NamedStrategy:
    """A strategy identified only by its name."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        name: str,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return self._metadata

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Return a placeholder outcome."""

        return StrategyOutcome(
            output=self.metadata.name,
        )


def completed_execution(
    strategy: Strategy,
    context: Context,
) -> ExecutionResult:
    """Return a successful execution that appends one completion event."""

    return ExecutionResult(
        strategy_id=strategy.metadata.id,
        strategy_name=strategy.metadata.name,
        strategy_version=strategy.metadata.version,
        output=strategy.metadata.name,
        initial_context=context,
        final_context=context.append(
            ContextEvent(
                event_type="workflow.step.completed",
                payload={
                    "strategy_name": strategy.metadata.name,
                },
                producer="concurrency-test",
            )
        ),
        started_at=EXECUTION_TIME,
        completed_at=EXECUTION_TIME,
    )


class RendezvousExecutor(StrategyExecutor):
    """Require every named strategy to be running at the same time.

    Each execution announces its arrival and then waits for every other
    participant. Executed one at a time, the first participant times out.
    """

    def __init__(
        self,
        *,
        participants: tuple[str, ...],
    ) -> None:
        self._arrivals = {name: asyncio.Event() for name in participants}
        self.calls: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Arrive, wait for every participant, then succeed."""

        name = strategy.metadata.name
        self.calls.append(name)

        if name in self._arrivals:
            self._arrivals[name].set()

            await asyncio.wait_for(
                asyncio.gather(*(arrival.wait() for arrival in self._arrivals.values())),
                timeout=RENDEZVOUS_TIMEOUT_SECONDS,
            )

        return completed_execution(
            strategy,
            context,
        )


class OrderedFinishExecutor(StrategyExecutor):
    """Finish named strategies in a configured order.

    Each strategy waits until every strategy before it in the finish order
    has completed, so the recorded completion order is exact.
    """

    def __init__(
        self,
        *,
        finish_order: tuple[str, ...],
        failing: frozenset[str] = NO_FAILURES,
    ) -> None:
        self._finish_order = finish_order
        self._failing = failing
        self._finished = {name: asyncio.Event() for name in finish_order}
        self.started: list[str] = []
        self.completed: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Wait for earlier finishers, then succeed or fail."""

        name = strategy.metadata.name
        self.started.append(name)

        if name in self._finish_order:
            for earlier in self._finish_order[: self._finish_order.index(name)]:
                await asyncio.wait_for(
                    self._finished[earlier].wait(),
                    timeout=RENDEZVOUS_TIMEOUT_SECONDS,
                )

        self.completed.append(name)

        if name in self._finished:
            self._finished[name].set()

        if name in self._failing:
            raise RuntimeError(f"{name} failed")

        return completed_execution(
            strategy,
            context,
        )


def create_candidate(
    *,
    left_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.FAIL_WORKFLOW,
    right_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.FAIL_WORKFLOW,
) -> WorkflowCandidate:
    """Create a workflow with three root steps and one downstream step."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Concurrent layer workflow",
            description="Exercise concurrent layer execution.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=LEFT_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=LEFT_STRATEGY_ID,
                    name="Left",
                ),
                failure_policy=left_policy,
            ),
            WorkflowCandidateStep(
                id=RIGHT_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=RIGHT_STRATEGY_ID,
                    name="Right",
                ),
                failure_policy=right_policy,
            ),
            WorkflowCandidateStep(
                id=THIRD_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=THIRD_STRATEGY_ID,
                    name="Third",
                ),
            ),
            WorkflowCandidateStep(
                id=DOWNSTREAM_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=DOWNSTREAM_STRATEGY_ID,
                    name="Downstream",
                ),
                depends_on=(
                    LEFT_STEP_ID,
                    RIGHT_STEP_ID,
                    THIRD_STEP_ID,
                ),
            ),
        ),
    )


def completed_strategy_names(
    context: Context,
) -> tuple[str, ...]:
    """Return the strategy names of completion events in context order."""

    names: list[str] = []

    for event in context.events:
        if event.event_type != "workflow.step.completed":
            continue

        name = event.payload["strategy_name"]

        assert isinstance(name, str)

        names.append(name)

    return tuple(names)


def test_steps_in_one_layer_run_concurrently() -> None:
    executor = RendezvousExecutor(
        participants=(
            "Left",
            "Right",
            "Third",
        ),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    assert run.succeeded

    assert all(step.status is WorkflowStepStatus.EXECUTED for step in run.steps)

    assert executor.calls[-1] == "Downstream"


def test_layer_steps_start_in_declared_order() -> None:
    executor = RendezvousExecutor(
        participants=(
            "Left",
            "Right",
            "Third",
        ),
    )

    asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    assert executor.calls == [
        "Left",
        "Right",
        "Third",
        "Downstream",
    ]


def test_layer_commits_in_declared_order_regardless_of_finish_order() -> None:
    executor = OrderedFinishExecutor(
        finish_order=(
            "Third",
            "Right",
            "Left",
        ),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    assert executor.completed[:3] == [
        "Third",
        "Right",
        "Left",
    ]

    assert tuple(step.step_id for step in run.steps) == (
        LEFT_STEP_ID,
        RIGHT_STEP_ID,
        THIRD_STEP_ID,
        DOWNSTREAM_STEP_ID,
    )

    assert completed_strategy_names(run.final_context) == (
        "Left",
        "Right",
        "Third",
        "Downstream",
    )


def test_concurrent_siblings_receive_the_same_layer_context() -> None:
    received: dict[str, Context] = {}

    class ContextRecordingExecutor(OrderedFinishExecutor):
        """Record the context each strategy receives."""

        async def execute(
            self,
            strategy: Strategy,
            context: Context,
        ) -> ExecutionResult:
            """Record the received context, then execute."""

            received[strategy.metadata.name] = context

            return await super().execute(
                strategy,
                context,
            )

    initial_context = Context()

    asyncio.run(
        WorkflowRunner(
            executor=ContextRecordingExecutor(
                finish_order=(
                    "Right",
                    "Left",
                    "Third",
                ),
            ),
        ).run(
            workflow=create_candidate(),
            context=initial_context,
        )
    )

    assert received["Left"] == initial_context
    assert received["Right"] == initial_context
    assert received["Third"] == initial_context

    assert completed_strategy_names(received["Downstream"]) == (
        "Left",
        "Right",
        "Third",
    )


def test_fail_workflow_lets_running_siblings_finish() -> None:
    executor = OrderedFinishExecutor(
        finish_order=(
            "Left",
            "Right",
            "Third",
        ),
        failing=frozenset({"Left"}),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run_recording_failures(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    assert run.failed

    assert tuple((step.step_id, step.status) for step in run.steps) == (
        (
            LEFT_STEP_ID,
            WorkflowStepStatus.FAILED,
        ),
        (
            RIGHT_STEP_ID,
            WorkflowStepStatus.EXECUTED,
        ),
        (
            THIRD_STEP_ID,
            WorkflowStepStatus.EXECUTED,
        ),
    )

    assert "Downstream" not in executor.started


def test_fail_workflow_commits_finished_sibling_context() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=OrderedFinishExecutor(
                finish_order=(
                    "Left",
                    "Right",
                    "Third",
                ),
                failing=frozenset({"Left"}),
            ),
        ).run_recording_failures(
            workflow=create_candidate(),
            context=Context(),
        )
    )

    assert completed_strategy_names(run.final_context) == (
        "Right",
        "Third",
    )


def test_fail_workflow_raises_after_siblings_finish() -> None:
    executor = OrderedFinishExecutor(
        finish_order=(
            "Left",
            "Right",
            "Third",
        ),
        failing=frozenset({"Left"}),
    )

    with pytest.raises(
        RuntimeError,
        match="Left failed",
    ):
        asyncio.run(
            WorkflowRunner(
                executor=executor,
            ).run(
                workflow=create_candidate(),
                context=Context(),
            )
        )

    assert executor.completed == [
        "Left",
        "Right",
        "Third",
    ]


def test_first_declared_fail_workflow_failure_is_raised() -> None:
    #
    # Right fails first in time, but Left is declared first, so Left's
    # failure is the one the run reports.
    #
    with pytest.raises(
        RuntimeError,
        match="Left failed",
    ):
        asyncio.run(
            WorkflowRunner(
                executor=OrderedFinishExecutor(
                    finish_order=(
                        "Right",
                        "Left",
                        "Third",
                    ),
                    failing=frozenset(
                        {
                            "Left",
                            "Right",
                        }
                    ),
                ),
            ).run(
                workflow=create_candidate(),
                context=Context(),
            )
        )


def test_continue_failure_in_concurrent_layer_runs_downstream() -> None:
    executor = OrderedFinishExecutor(
        finish_order=(
            "Third",
            "Left",
            "Right",
        ),
        failing=frozenset({"Left"}),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(
                left_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            context=Context(),
        )
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.EXECUTED,
    )

    assert executor.started[-1] == "Downstream"


def test_skip_dependents_failure_in_concurrent_layer_skips_downstream() -> None:
    executor = OrderedFinishExecutor(
        finish_order=(
            "Right",
            "Third",
            "Left",
        ),
        failing=frozenset({"Left"}),
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(
                left_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
            ),
            context=Context(),
        )
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.SKIPPED,
    )

    assert "Downstream" not in executor.started

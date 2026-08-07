"""Tests for workflow execution orchestration."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

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
    WorkflowMetadata,
    WorkflowRunner,
)

WORKFLOW_ID = UUID("7af83b9b-9dc2-4729-9165-7a3702f0d758")

STEP_ONE_ID = UUID("3c903a80-2f48-45d2-8f1c-d67a13b6c96b")
STEP_TWO_ID = UUID("c95c5d69-9f95-4dc5-b7e5-36bc2f2a6488")

STRATEGY_ONE_ID = UUID("152bf0b4-3bbc-4aaa-9959-79fd09c41904")
STRATEGY_TWO_ID = UUID("cb04e136-f865-4528-8651-8bbfdb6ec101")


class StubStrategy:
    """A minimal executable strategy used by workflow runner tests."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        name: str,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Execute the {name} workflow step.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return stable strategy metadata."""

        return self._metadata

    async def run(self, context: Context) -> StrategyOutcome:
        """Return a deterministic placeholder outcome."""

        return StrategyOutcome(
            output=self.metadata.name,
        )


class RecordingExecutor(StrategyExecutor):
    """A strategy executor that records workflow orchestration calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[Strategy, Context]] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record execution and append a deterministic context event."""

        self.calls.append((strategy, context))

        call_index = len(self.calls)

        started_at = datetime(
            2026,
            8,
            6,
            23,
            0,
            call_index,
            tzinfo=UTC,
        )
        completed_at = datetime(
            2026,
            8,
            6,
            23,
            0,
            call_index + 1,
            tzinfo=UTC,
        )

        final_context = context.append(
            ContextEvent(
                event_type="workflow.step.completed",
                payload={
                    "strategy_name": strategy.metadata.name,
                    "call_index": call_index,
                },
                producer="recording-executor",
            )
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=strategy.metadata.name,
            initial_context=context,
            final_context=final_context,
            started_at=started_at,
            completed_at=completed_at,
        )


def create_candidate() -> WorkflowCandidate:
    """Create a deterministic executable workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Support workflow",
            description="Classify and resolve a support request.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ONE_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_ONE_ID,
                    name="Classifier",
                ),
            ),
            WorkflowCandidateStep(
                id=STEP_TWO_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_TWO_ID,
                    name="Reasoner",
                ),
                depends_on=(STEP_ONE_ID,),
            ),
        ),
    )


def test_runner_returns_complete_workflow_run() -> None:
    candidate = create_candidate()
    context = Context()
    executor = RecordingExecutor()
    runner = WorkflowRunner(
        executor=executor,
    )

    run = asyncio.run(
        runner.run(
            workflow=candidate,
            context=context,
        )
    )

    assert run.workflow == candidate.metadata
    assert run.initial_context == context

    assert len(run.final_context.events) == 2
    assert tuple(event.payload["strategy_name"] for event in run.final_context.events) == (
        "Classifier",
        "Reasoner",
    )

    assert len(run.steps) == 2

    assert tuple(step.step_id for step in run.steps) == (
        STEP_ONE_ID,
        STEP_TWO_ID,
    )

    assert tuple(step.execution.strategy_name for step in run.steps) == (
        "Classifier",
        "Reasoner",
    )

    assert tuple(step.layer_index for step in run.steps) == (
        0,
        1,
    )


def test_runner_executes_steps_in_candidate_order() -> None:
    candidate = create_candidate()
    executor = RecordingExecutor()
    runner = WorkflowRunner(
        executor=executor,
    )

    asyncio.run(
        runner.run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(strategy.metadata.name for strategy, _ in executor.calls) == (
        "Classifier",
        "Reasoner",
    )


def test_runner_passes_each_step_the_previous_final_context() -> None:
    candidate = create_candidate()
    initial_context = Context()
    executor = RecordingExecutor()
    runner = WorkflowRunner(
        executor=executor,
    )

    asyncio.run(
        runner.run(
            workflow=candidate,
            context=initial_context,
        )
    )

    first_received_context = executor.calls[0][1]
    second_received_context = executor.calls[1][1]

    assert first_received_context == initial_context

    assert tuple(
        event.payload["strategy_name"]
        for event in second_received_context.events
        if event.event_type == "workflow.step.completed"
    ) == ("Classifier",)


def test_runner_records_workflow_step_and_strategy_identities() -> None:
    candidate = create_candidate()
    runner = WorkflowRunner(
        executor=RecordingExecutor(),
    )

    run = asyncio.run(
        runner.run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(step.step_id for step in run.steps) == (
        STEP_ONE_ID,
        STEP_TWO_ID,
    )

    assert tuple(step.execution.strategy_id for step in run.steps) == (
        STRATEGY_ONE_ID,
        STRATEGY_TWO_ID,
    )

    assert all(step.step_id != step.execution.strategy_id for step in run.steps)


def test_runner_records_each_strategy_execution() -> None:
    candidate = create_candidate()
    runner = WorkflowRunner(
        executor=RecordingExecutor(),
    )

    run = asyncio.run(
        runner.run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(step.execution.output for step in run.steps) == (
        "Classifier",
        "Reasoner",
    )


def test_runner_records_sequential_layer_indexes() -> None:
    candidate = create_candidate()
    runner = WorkflowRunner(
        executor=RecordingExecutor(),
    )

    run = asyncio.run(
        runner.run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(step.layer_index for step in run.steps) == (
        0,
        1,
    )

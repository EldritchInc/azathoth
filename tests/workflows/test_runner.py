"""Tests for workflow execution orchestration."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import JsonValue

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
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowValueBinding,
    WorkflowValueReference,
    WorkflowValueResolutionError,
)

WORKFLOW_ID = UUID("7af83b9b-9dc2-4729-9165-7a3702f0d758")

STEP_ONE_ID = UUID("3c903a80-2f48-45d2-8f1c-d67a13b6c96b")
STEP_TWO_ID = UUID("c95c5d69-9f95-4dc5-b7e5-36bc2f2a6488")
STEP_THREE_ID = UUID("45c1b891-d098-4e42-9abc-e7422159f0f7")
STEP_FOUR_ID = UUID("04394e6d-bfa8-4b05-b226-c540182e24dd")

STRATEGY_ONE_ID = UUID("152bf0b4-3bbc-4aaa-9959-79fd09c41904")
STRATEGY_TWO_ID = UUID("cb04e136-f865-4528-8651-8bbfdb6ec101")
STRATEGY_THREE_ID = UUID("325ee8d4-3d92-4792-86ee-cba7169a36ed")
STRATEGY_FOUR_ID = UUID("b20c8f9a-a381-440c-a821-07589709131e")


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

    def __init__(
        self,
        *,
        fail_on: str | None = None,
    ) -> None:
        self.calls: list[tuple[Strategy, Context]] = []
        self.fail_on = fail_on

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record execution and optionally fail a configured strategy."""

        self.calls.append((strategy, context))

        if strategy.metadata.name == self.fail_on:
            raise RuntimeError(f"{strategy.metadata.name} failed")

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


class WorkflowInputRecordingExecutor(StrategyExecutor):
    """Record resolved workflow inputs received by strategies."""

    def __init__(self) -> None:
        self.calls: list[tuple[Strategy, Context]] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        self.calls.append((strategy, context))

        input_values: dict[str, JsonValue] = {}

        for event in context.events:
            if event.event_type != "workflow.input.bound":
                continue

            name = event.payload["name"]
            value = event.payload["value"]

            assert isinstance(name, str)

            input_values[name] = value

        started_at = datetime(
            2026,
            8,
            9,
            16,
            0,
            tzinfo=UTC,
        )
        completed_at = datetime(
            2026,
            8,
            9,
            16,
            0,
            1,
            tzinfo=UTC,
        )

        output: JsonValue

        if strategy.metadata.name == "Classifier":
            output = {
                "classification": "math",
            }
        else:
            output = {
                "received_inputs": input_values,
            }

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=output,
            initial_context=context,
            final_context=context,
            started_at=started_at,
            completed_at=completed_at,
        )


class StructuredOutputExecutor(StrategyExecutor):
    """Return deterministic structured workflow outputs."""

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        started_at = datetime(
            2026,
            8,
            8,
            21,
            0,
            tzinfo=UTC,
        )
        completed_at = datetime(
            2026,
            8,
            8,
            21,
            0,
            1,
            tzinfo=UTC,
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output={
                "classification": "math",
                "confidence": 0.98,
            },
            initial_context=context,
            final_context=context,
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


def create_value_candidate() -> WorkflowCandidate:
    """Create a candidate that exports structured workflow values."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Value workflow",
            description="Export structured execution outputs.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ONE_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_ONE_ID,
                    name="Classifier",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                        path=("classification",),
                    ),
                    WorkflowValueBinding(
                        name="confidence",
                        path=("confidence",),
                    ),
                ),
            ),
        ),
    )


def create_layered_candidate() -> WorkflowCandidate:
    """Create a workflow with two independent root steps."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Layered support workflow",
            description="Classify independently before reasoning.",
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
                    name="Question detector",
                ),
            ),
            WorkflowCandidateStep(
                id=STEP_THREE_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_THREE_ID,
                    name="Reasoner",
                ),
                depends_on=(
                    STEP_ONE_ID,
                    STEP_TWO_ID,
                ),
            ),
        ),
    )


def create_three_layer_candidate() -> WorkflowCandidate:
    """Create a workflow with three dependency layers."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Three-layer support workflow",
            description="Prepare, classify, and resolve a request.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ONE_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_ONE_ID,
                    name="Preparation",
                ),
            ),
            WorkflowCandidateStep(
                id=STEP_TWO_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_TWO_ID,
                    name="Classifier",
                ),
                depends_on=(STEP_ONE_ID,),
            ),
            WorkflowCandidateStep(
                id=STEP_THREE_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_THREE_ID,
                    name="Question detector",
                ),
                depends_on=(STEP_ONE_ID,),
            ),
            WorkflowCandidateStep(
                id=STEP_FOUR_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_FOUR_ID,
                    name="Reasoner",
                ),
                depends_on=(
                    STEP_TWO_ID,
                    STEP_THREE_ID,
                ),
            ),
        ),
    )


def create_value_flow_candidate() -> WorkflowCandidate:
    """Create a workflow whose downstream step consumes an upstream value."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Workflow value flow",
            description="Export and consume a workflow value.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ONE_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_ONE_ID,
                    name="Classifier",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                        path=("classification",),
                    ),
                ),
            ),
            WorkflowCandidateStep(
                id=STEP_TWO_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_TWO_ID,
                    name="Reasoner",
                ),
                depends_on=(STEP_ONE_ID,),
                inputs=(
                    WorkflowInputBinding(
                        name="route",
                        source=WorkflowValueReference(
                            producer_step_id=STEP_ONE_ID,
                            name="classification",
                        ),
                    ),
                ),
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


def test_runner_passes_next_layer_the_previous_layer_final_context() -> None:
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


def test_steps_in_same_layer_receive_same_starting_context() -> None:
    candidate = create_layered_candidate()
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

    classifier_context = executor.calls[0][1]
    question_context = executor.calls[1][1]

    assert classifier_context == initial_context
    assert question_context == initial_context


def test_next_layer_receives_merged_previous_layer_context() -> None:
    candidate = create_layered_candidate()
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

    reasoning_context = executor.calls[2][1]

    assert tuple(
        event.payload["strategy_name"]
        for event in reasoning_context.events
        if event.event_type == "workflow.step.completed"
    ) == (
        "Classifier",
        "Question detector",
    )


def test_runner_records_dependency_layer_indexes() -> None:
    candidate = create_layered_candidate()

    run = asyncio.run(
        WorkflowRunner(
            executor=RecordingExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(step.layer_index for step in run.steps) == (
        0,
        0,
        1,
    )


def test_runner_merges_layer_events_without_duplication() -> None:
    candidate = create_layered_candidate()

    run = asyncio.run(
        WorkflowRunner(
            executor=RecordingExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    names = tuple(
        event.payload["strategy_name"]
        for event in run.final_context.events
        if event.event_type == "workflow.step.completed"
    )

    assert names == (
        "Classifier",
        "Question detector",
        "Reasoner",
    )


def test_root_failure_prevents_downstream_execution() -> None:
    candidate = create_candidate()
    executor = RecordingExecutor(
        fail_on="Classifier",
    )
    runner = WorkflowRunner(
        executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="Classifier failed",
    ):
        asyncio.run(
            runner.run(
                workflow=candidate,
                context=Context(),
            )
        )

    assert tuple(strategy.metadata.name for strategy, _ in executor.calls) == ("Classifier",)


def test_failed_layer_does_not_execute_downstream_layers() -> None:
    candidate = create_layered_candidate()
    executor = RecordingExecutor(
        fail_on="Question detector",
    )
    runner = WorkflowRunner(
        executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="Question detector failed",
    ):
        asyncio.run(
            runner.run(
                workflow=candidate,
                context=Context(),
            )
        )

    assert tuple(strategy.metadata.name for strategy, _ in executor.calls) == (
        "Classifier",
        "Question detector",
    )


def test_failed_layer_does_not_expose_partial_context_to_siblings() -> None:
    candidate = create_layered_candidate()
    initial_context = Context()
    executor = RecordingExecutor(
        fail_on="Question detector",
    )
    runner = WorkflowRunner(
        executor=executor,
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            runner.run(
                workflow=candidate,
                context=initial_context,
            )
        )

    classifier_context = executor.calls[0][1]
    question_context = executor.calls[1][1]

    assert classifier_context == initial_context
    assert question_context == initial_context
    assert classifier_context == question_context


def test_original_strategy_exception_is_preserved() -> None:
    candidate = create_candidate()
    executor = RecordingExecutor(
        fail_on="Classifier",
    )
    runner = WorkflowRunner(
        executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="Classifier failed",
    ):
        asyncio.run(
            runner.run(
                workflow=candidate,
                context=Context(),
            )
        )


def test_completed_layer_context_reaches_later_failing_layer() -> None:
    candidate = create_three_layer_candidate()
    executor = RecordingExecutor(
        fail_on="Question detector",
    )
    runner = WorkflowRunner(
        executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="Question detector failed",
    ):
        asyncio.run(
            runner.run(
                workflow=candidate,
                context=Context(),
            )
        )

    classifier_context = executor.calls[1][1]
    question_context = executor.calls[2][1]

    assert classifier_context == question_context

    assert tuple(
        event.payload["strategy_name"]
        for event in classifier_context.events
        if event.event_type == "workflow.step.completed"
    ) == ("Preparation",)


def test_failure_prevents_future_layers_from_executing() -> None:
    candidate = create_three_layer_candidate()
    executor = RecordingExecutor(
        fail_on="Question detector",
    )
    runner = WorkflowRunner(
        executor=executor,
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            runner.run(
                workflow=candidate,
                context=Context(),
            )
        )

    assert tuple(strategy.metadata.name for strategy, _ in executor.calls) == (
        "Preparation",
        "Classifier",
        "Question detector",
    )

    assert all(strategy.metadata.name != "Reasoner" for strategy, _ in executor.calls)


def test_runner_records_empty_workflow_values() -> None:
    candidate = create_candidate()

    run = asyncio.run(
        WorkflowRunner(
            executor=RecordingExecutor(),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    assert tuple(step.values for step in run.steps) == (
        (),
        (),
    )


def test_runner_populates_declared_workflow_values() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=StructuredOutputExecutor(),
        ).run(
            workflow=create_value_candidate(),
            context=Context(),
        )
    )

    assert tuple((value.name, value.value) for value in run.steps[0].values) == (
        ("classification", "math"),
        ("confidence", 0.98),
    )

    assert all(value.producer_step_id == STEP_ONE_ID for value in run.steps[0].values)


def test_runner_values_are_exposed_by_workflow_run() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=StructuredOutputExecutor(),
        ).run(
            workflow=create_value_candidate(),
            context=Context(),
        )
    )

    classifications = run.values_named("classification")

    assert len(classifications) == 1
    assert classifications[0].value == "math"
    assert classifications[0].producer_step_id == STEP_ONE_ID


def test_runner_fails_when_declared_output_cannot_be_resolved() -> None:
    candidate = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Invalid value workflow",
            description="Declare a missing output path.",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ONE_ID,
                strategy=StubStrategy(
                    strategy_id=STRATEGY_ONE_ID,
                    name="Classifier",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="missing",
                        path=("does_not_exist",),
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(
        WorkflowValueResolutionError,
        match="does_not_exist",
    ):
        asyncio.run(
            WorkflowRunner(
                executor=StructuredOutputExecutor(),
            ).run(
                workflow=candidate,
                context=Context(),
            )
        )


def test_runner_resolves_workflow_inputs_from_upstream_values() -> None:
    executor = WorkflowInputRecordingExecutor()

    asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_value_flow_candidate(),
            context=Context(),
        )
    )

    reasoner_context = executor.calls[1][1]

    input_events = tuple(
        event for event in reasoner_context.events if event.event_type == "workflow.input.bound"
    )

    assert len(input_events) == 1

    assert input_events[0].payload["name"] == "route"
    assert input_events[0].payload["value"] == "math"
    assert input_events[0].payload["source_name"] == "classification"
    assert input_events[0].payload["producer_step_id"] == str(STEP_ONE_ID)


def test_workflow_input_events_are_not_committed_to_shared_context() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=WorkflowInputRecordingExecutor(),
        ).run(
            workflow=create_value_flow_candidate(),
            context=Context(),
        )
    )

    assert all(event.event_type != "workflow.input.bound" for event in run.final_context.events)


def test_consumed_workflow_value_remains_in_workflow_run() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=WorkflowInputRecordingExecutor(),
        ).run(
            workflow=create_value_flow_candidate(),
            context=Context(),
        )
    )

    values = run.values_named("classification")

    assert len(values) == 1
    assert values[0].value == "math"
    assert values[0].producer_step_id == STEP_ONE_ID

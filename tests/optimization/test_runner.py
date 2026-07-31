"""Tests for optimization execution and evaluation orchestration."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import Context, ContextEvent
from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    EvaluatorMetadata,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.execution import ExecutionResult
from azathoth.goals import Goal
from azathoth.optimization import (
    OptimizationExample,
    OptimizationRunner,
)
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)


class RecordingExecutor:
    """A test executor that records its inputs."""

    def __init__(self, result: ExecutionResult) -> None:
        self.result = result
        self.received_strategy: Strategy | None = None
        self.received_context: Context | None = None

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        self.received_strategy = strategy
        self.received_context = context
        return self.result


class RecordingEvaluator:
    """A test evaluator that records its inputs."""

    def __init__(self, result: EvaluationResult) -> None:
        self._metadata = EvaluatorMetadata(
            name="recording-evaluator",
            description="Record evaluator inputs for runner tests.",
            version="1.0.0",
        )
        self.result = result
        self.received_expected: ExpectedOutcome | None = None
        self.received_actual: JsonValue = None

    @property
    def metadata(self) -> EvaluatorMetadata:
        return self._metadata

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        self.received_expected = expected
        self.received_actual = actual
        return self.result


class StubStrategy:
    """A minimal strategy used by optimization runner tests."""

    def __init__(self) -> None:
        self._metadata = StrategyMetadata(
            id=UUID("d8204efd-8874-494d-98cb-035eac8cf24c"),
            name="Test strategy",
            description="A strategy used by optimization runner tests.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        return self._metadata

    async def run(self, _context: Context) -> StrategyOutcome:
        return StrategyOutcome(output=None)


def create_example() -> OptimizationExample:
    """Create a deterministic optimization example."""

    return OptimizationExample(
        id=UUID("cf87282e-cbd0-44b5-864d-c599fb4d65a7"),
        name="Classify duplicate charge",
        goal=Goal(
            id=UUID("78bdb052-c598-4c39-af88-f4b4463dbc1e"),
            name="Classify support intent",
            description="Identify the intent of a support request.",
            success_criteria=("The expected support category is returned.",),
        ),
        context=Context(
            events=(
                ContextEvent(
                    event_type="customer.message.received",
                    payload={
                        "message": "I was charged twice.",
                    },
                    producer="test-suite",
                ),
            )
        ),
        expected_outcome=ExpectedOutcome(
            description="The request is classified as a duplicate charge.",
            value="duplicate_charge",
            comparison=OutcomeComparison.EXACT,
        ),
    )


def create_execution_result(
    example: OptimizationExample,
) -> ExecutionResult:
    """Create a deterministic execution result."""

    return ExecutionResult(
        strategy_id=UUID("d8204efd-8874-494d-98cb-035eac8cf24c"),
        strategy_name="Test strategy",
        strategy_version="1.0.0",
        output="duplicate_charge",
        initial_context=example.context,
        final_context=example.context,
        started_at=datetime(
            2026,
            7,
            31,
            13,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            7,
            31,
            13,
            0,
            1,
            tzinfo=UTC,
        ),
    )


def create_evaluation_result() -> EvaluationResult:
    """Create a deterministic passing evaluation result."""

    return EvaluationResult(
        id=UUID("58fcdca7-bc98-41cf-9289-37f799db1966"),
        evaluator_name="recording-evaluator",
        evaluator_version="1.0.0",
        score=1.0,
        threshold=1.0,
        status=EvaluationStatus.PASSED,
        reason="The values matched.",
        evidence=(
            EvaluationEvidence(
                label="expected",
                value="duplicate_charge",
            ),
            EvaluationEvidence(
                label="actual",
                value="duplicate_charge",
            ),
        ),
    )


def create_timestamps() -> Iterator[datetime]:
    """Create deterministic start and completion timestamps."""

    return iter(
        (
            datetime(
                2026,
                7,
                31,
                13,
                0,
                tzinfo=UTC,
            ),
            datetime(
                2026,
                7,
                31,
                13,
                0,
                2,
                tzinfo=UTC,
            ),
        )
    )


def test_runner_returns_complete_optimization_run() -> None:
    example = create_example()
    execution = create_execution_result(example)
    evaluation = create_evaluation_result()

    executor = RecordingExecutor(execution)
    evaluator = RecordingEvaluator(evaluation)
    strategy = StubStrategy()

    timestamps = iter(
        (
            datetime(
                2026,
                7,
                31,
                12,
                59,
                59,
                tzinfo=UTC,
            ),
            datetime(
                2026,
                7,
                31,
                13,
                0,
                2,
                tzinfo=UTC,
            ),
        )
    )

    runner = OptimizationRunner(
        executor=executor,
        clock=lambda: next(timestamps),
    )

    run = asyncio.run(
        runner.run(
            example=example,
            strategy=strategy,
            evaluator=evaluator,
        )
    )

    assert run.example_id == example.id
    assert run.execution == execution
    assert run.evaluation == evaluation
    assert run.passed is True
    assert run.started_at == datetime(
        2026,
        7,
        31,
        12,
        59,
        59,
        tzinfo=UTC,
    )
    assert run.completed_at == datetime(
        2026,
        7,
        31,
        13,
        0,
        2,
        tzinfo=UTC,
    )


def test_runner_executes_strategy_against_example_context() -> None:
    example = create_example()
    executor = RecordingExecutor(create_execution_result(example))
    evaluator = RecordingEvaluator(create_evaluation_result())
    strategy = StubStrategy()
    timestamps = create_timestamps()

    runner = OptimizationRunner(
        executor=executor,
        clock=lambda: next(timestamps),
    )

    asyncio.run(
        runner.run(
            example=example,
            strategy=strategy,
            evaluator=evaluator,
        )
    )

    assert executor.received_strategy is strategy
    assert executor.received_context == example.context


def test_runner_evaluates_execution_output_against_expected_outcome() -> None:
    example = create_example()
    execution = create_execution_result(example)

    executor = RecordingExecutor(execution)
    evaluator = RecordingEvaluator(create_evaluation_result())
    timestamps = create_timestamps()

    runner = OptimizationRunner(
        executor=executor,
        clock=lambda: next(timestamps),
    )

    asyncio.run(
        runner.run(
            example=example,
            strategy=StubStrategy(),
            evaluator=evaluator,
        )
    )

    assert evaluator.received_expected == example.expected_outcome
    assert evaluator.received_actual == execution.output

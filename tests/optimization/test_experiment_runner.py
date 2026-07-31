"""Tests for running candidate strategies across optimization examples."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.evaluation import (
    EvaluationResult,
    EvaluationStatus,
    Evaluator,
    EvaluatorMetadata,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.execution import ExecutionResult
from azathoth.goals import Goal
from azathoth.optimization import (
    ExperimentRunner,
    OptimizationExample,
    OptimizationRun,
)
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)

STRATEGY_A_ID = UUID("3a114bd2-a105-46dd-93e6-db155d101f22")
STRATEGY_B_ID = UUID("62c21510-74e2-4812-80c8-481852a03f76")

EXAMPLE_1_ID = UUID("4659ec55-e131-4da9-b410-88b6066c1a81")
EXAMPLE_2_ID = UUID("f741aa92-e982-4933-994c-ed28eeb33940")
EXAMPLE_3_ID = UUID("130ff2a6-fecd-471a-940b-1885fec811bb")


class StubStrategy:
    """A minimal strategy used to identify experiment candidates."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        name: str,
        version: str = "1.0.0",
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Test strategy named {name}.",
            version=version,
        )

    @property
    def metadata(self) -> StrategyMetadata:
        return self._metadata

    async def run(self, context: Context) -> StrategyOutcome:
        """Return a placeholder result.

        The recording optimization runner does not call this method.
        """

        return StrategyOutcome(output=None)


class StubEvaluator:
    """A minimal evaluator used to satisfy the experiment contract."""

    def __init__(self) -> None:
        self._metadata = EvaluatorMetadata(
            name="stub-evaluator",
            description="Evaluator used by experiment runner tests.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> EvaluatorMetadata:
        return self._metadata

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult:
        """Return a deterministic passing evaluation."""

        return EvaluationResult(
            evaluator_name=self.metadata.name,
            evaluator_version=self.metadata.version,
            score=1.0,
            threshold=1.0,
            status=EvaluationStatus.PASSED,
            reason="Stub evaluator always passes.",
        )


class RecordingOptimizationRunner:
    """A test runner that records each example-strategy pair."""

    def __init__(self) -> None:
        self.calls: list[tuple[OptimizationExample, Strategy, Evaluator]] = []

    async def run(
        self,
        example: OptimizationExample,
        strategy: Strategy,
        evaluator: Evaluator,
    ) -> OptimizationRun:
        """Record the request and return a matching optimization run."""

        self.calls.append((example, strategy, evaluator))

        now = datetime(
            2026,
            7,
            31,
            15,
            0,
            tzinfo=UTC,
        )

        execution = ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=example.expected_outcome.value,
            initial_context=example.context,
            final_context=example.context,
            started_at=now,
            completed_at=now,
        )

        evaluation = EvaluationResult(
            evaluator_name=evaluator.metadata.name,
            evaluator_version=evaluator.metadata.version,
            score=1.0,
            threshold=1.0,
            status=EvaluationStatus.PASSED,
            reason="Recorded experiment run passed.",
        )

        return OptimizationRun(
            example_id=example.id,
            execution=execution,
            evaluation=evaluation,
            started_at=now,
            completed_at=now,
        )


def create_example(
    *,
    example_id: UUID,
    name: str,
    expected_value: str,
) -> OptimizationExample:
    """Create a deterministic optimization example."""

    return OptimizationExample(
        id=example_id,
        name=name,
        goal=Goal(
            name="Classify support intent",
            description="Return the expected support category.",
            success_criteria=("The predicted category matches the expected category.",),
        ),
        context=Context(),
        expected_outcome=ExpectedOutcome(
            description="The expected support category is returned.",
            value=expected_value,
            comparison=OutcomeComparison.EXACT,
        ),
    )


def create_examples() -> tuple[OptimizationExample, ...]:
    """Create three deterministic experiment examples."""

    return (
        create_example(
            example_id=EXAMPLE_1_ID,
            name="Duplicate charge",
            expected_value="duplicate_charge",
        ),
        create_example(
            example_id=EXAMPLE_2_ID,
            name="Refund request",
            expected_value="refund_request",
        ),
        create_example(
            example_id=EXAMPLE_3_ID,
            name="Account access",
            expected_value="account_access",
        ),
    )


def create_strategies() -> tuple[StubStrategy, ...]:
    """Create two deterministic candidate strategies."""

    return (
        StubStrategy(
            strategy_id=STRATEGY_A_ID,
            name="Strategy A",
        ),
        StubStrategy(
            strategy_id=STRATEGY_B_ID,
            name="Strategy B",
        ),
    )


def test_experiment_runner_returns_one_scorecard_for_one_strategy() -> None:
    examples = create_examples()
    strategy = create_strategies()[0]
    evaluator = StubEvaluator()
    optimization_runner = RecordingOptimizationRunner()

    runner = ExperimentRunner(
        optimization_runner=optimization_runner,
    )

    scorecards = asyncio.run(
        runner.run(
            examples=examples,
            strategies=(strategy,),
            evaluator=evaluator,
        )
    )

    assert len(scorecards) == 1

    scorecard = scorecards[0]

    assert scorecard.strategy == strategy.metadata
    assert scorecard.run_count == 3
    assert scorecard.passed_count == 3
    assert scorecard.pass_rate == 1.0
    assert scorecard.mean_score == 1.0


def test_experiment_runner_runs_every_strategy_against_every_example() -> None:
    examples = create_examples()
    strategies = create_strategies()
    evaluator = StubEvaluator()
    optimization_runner = RecordingOptimizationRunner()

    runner = ExperimentRunner(
        optimization_runner=optimization_runner,
    )

    scorecards = asyncio.run(
        runner.run(
            examples=examples,
            strategies=strategies,
            evaluator=evaluator,
        )
    )

    assert len(scorecards) == 2
    assert all(scorecard.run_count == 3 for scorecard in scorecards)
    assert len(optimization_runner.calls) == 6


def test_experiment_runner_preserves_strategy_order() -> None:
    examples = create_examples()
    strategies = create_strategies()

    runner = ExperimentRunner(
        optimization_runner=RecordingOptimizationRunner(),
    )

    scorecards = asyncio.run(
        runner.run(
            examples=examples,
            strategies=strategies,
            evaluator=StubEvaluator(),
        )
    )

    assert tuple(scorecard.strategy.id for scorecard in scorecards) == (
        STRATEGY_A_ID,
        STRATEGY_B_ID,
    )


def test_experiment_runner_preserves_example_order_within_scorecard() -> None:
    examples = create_examples()
    strategy = create_strategies()[0]

    runner = ExperimentRunner(
        optimization_runner=RecordingOptimizationRunner(),
    )

    scorecards = asyncio.run(
        runner.run(
            examples=examples,
            strategies=(strategy,),
            evaluator=StubEvaluator(),
        )
    )

    assert tuple(run.example_id for run in scorecards[0].runs) == (
        EXAMPLE_1_ID,
        EXAMPLE_2_ID,
        EXAMPLE_3_ID,
    )


def test_experiment_runner_forwards_evaluator_to_every_run() -> None:
    examples = create_examples()
    strategies = create_strategies()
    evaluator = StubEvaluator()
    optimization_runner = RecordingOptimizationRunner()

    runner = ExperimentRunner(
        optimization_runner=optimization_runner,
    )

    asyncio.run(
        runner.run(
            examples=examples,
            strategies=strategies,
            evaluator=evaluator,
        )
    )

    assert all(
        received_evaluator is evaluator for _, _, received_evaluator in optimization_runner.calls
    )


def test_experiment_runner_returns_empty_tuple_for_no_examples() -> None:
    runner = ExperimentRunner(
        optimization_runner=RecordingOptimizationRunner(),
    )

    scorecards = asyncio.run(
        runner.run(
            examples=(),
            strategies=create_strategies(),
            evaluator=StubEvaluator(),
        )
    )

    assert scorecards == ()


def test_experiment_runner_returns_empty_tuple_for_no_strategies() -> None:
    runner = ExperimentRunner(
        optimization_runner=RecordingOptimizationRunner(),
    )

    scorecards = asyncio.run(
        runner.run(
            examples=create_examples(),
            strategies=(),
            evaluator=StubEvaluator(),
        )
    )

    assert scorecards == ()

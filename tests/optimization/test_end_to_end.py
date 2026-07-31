import asyncio
from uuid import UUID

from azathoth.context import Context, ContextEvent
from azathoth.evaluation import (
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.goals import Goal
from azathoth.optimization import (
    OptimizationExample,
    OptimizationRunner,
)
from azathoth.strategies import (
    EventFieldStrategy,
    StrategyMetadata,
)


def test_complete_optimization_pipeline() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={
                    "intent": "duplicate_charge",
                },
                producer="test-suite",
            ),
        )
    )

    example = OptimizationExample(
        name="Extract support intent",
        goal=Goal(
            name="Support classification",
            description="Extract the customer's intent.",
            success_criteria=("The customer intent is extracted from context.",),
        ),
        context=context,
        expected_outcome=ExpectedOutcome(
            description="The strategy extracts the intent.",
            value="duplicate_charge",
            comparison=OutcomeComparison.EXACT,
        ),
    )

    strategy = EventFieldStrategy(
        metadata=StrategyMetadata(
            id=UUID("d8204efd-8874-494d-98cb-035eac8cf24c"),
            name="Extract support intent",
            description="Extract the intent field from a context event.",
            version="1.0.0",
        ),
        event_type="customer.message.received",
        field_name="intent",
    )

    evaluator = ExactMatchEvaluator()

    runner = OptimizationRunner()

    run = asyncio.run(
        runner.run(
            example=example,
            strategy=strategy,
            evaluator=evaluator,
        )
    )

    assert run.passed

    assert run.execution.output == "duplicate_charge"

    assert run.evaluation.score == 1.0

    assert run.evaluation.passed

    assert run.execution.final_context.events[-1].event_type == "strategy.execution.completed"

    assert run.evaluation.evaluator_name == "exact-match"


def test_complete_pipeline_failure() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={
                    "intent": "duplicate_charge",
                },
                producer="test-suite",
            ),
        )
    )

    example = OptimizationExample(
        name="Extract support intent",
        goal=Goal(
            name="Support classification",
            description="Extract the customer's intent.",
            success_criteria=("The customer intent is extracted from context.",),
        ),
        context=context,
        expected_outcome=ExpectedOutcome(
            description="The strategy extracts the intent.",
            value="refund",
            comparison=OutcomeComparison.EXACT,
        ),
    )

    strategy = EventFieldStrategy(
        metadata=StrategyMetadata(
            id=UUID("d8204efd-8874-494d-98cb-035eac8cf24c"),
            name="Extract support intent",
            description="Extract the intent field from a context event.",
            version="1.0.0",
        ),
        event_type="customer.message.received",
        field_name="intent",
    )

    evaluator = ExactMatchEvaluator()

    runner = OptimizationRunner()

    run = asyncio.run(
        runner.run(
            example=example,
            strategy=strategy,
            evaluator=evaluator,
        )
    )

    assert not run.passed

    assert run.evaluation.score == 0.0

    assert run.evaluation.status.name == "FAILED"

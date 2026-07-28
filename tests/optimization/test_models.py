"""Tests for optimization example models."""

from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context, ContextEvent
from azathoth.evaluation import ExpectedOutcome, OutcomeComparison
from azathoth.goals import Goal
from azathoth.optimization import OptimizationExample


def test_optimization_example_round_trips_through_json() -> None:
    goal = Goal(
        id=UUID("3b53828b-0e3b-4f3e-8da4-5c9742707e0c"),
        name="Classify customer support requests",
        description="Identify the most appropriate support category.",
        success_criteria=(
            "The predicted category matches the expected category.",
            "The output contains only a valid category identifier.",
        ),
        constraints=("Do not expose private customer information.",),
    )

    context = Context(
        events=(
            ContextEvent(
                id=UUID("d018d96c-37d5-43c8-8576-4ae27ba6389d"),
                event_type="customer.message.received",
                payload={"message": "I was charged twice for the same order."},
                producer="test-fixture",
                provenance="support-example-001",
                occurred_at=datetime(
                    2026,
                    7,
                    28,
                    14,
                    0,
                    tzinfo=UTC,
                ),
            ),
        )
    )

    expected_outcome = ExpectedOutcome(
        description="The message is classified as a duplicate charge.",
        value="duplicate_charge",
        comparison=OutcomeComparison.EXACT,
    )

    example = OptimizationExample(
        id=UUID("92e0acee-f966-42a3-bca2-bc4bdfc9e7c8"),
        name="Duplicate billing charge",
        goal=goal,
        context=context,
        expected_outcome=expected_outcome,
        tags=("billing", "classification"),
    )

    serialized = example.model_dump_json()
    restored = OptimizationExample.model_validate_json(serialized)

    assert restored == example

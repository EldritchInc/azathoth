"""End-to-end execution test for a deterministic strategy."""

import asyncio
from datetime import UTC, datetime

from azathoth.context import Context, ContextEvent
from azathoth.execution import StrategyExecutor
from azathoth.strategies import EventFieldStrategy, StrategyMetadata


def test_executor_runs_event_field_strategy_end_to_end() -> None:
    timestamps = iter(
        (
            datetime(2026, 7, 28, 15, 0, tzinfo=UTC),
            datetime(2026, 7, 28, 15, 0, 1, tzinfo=UTC),
        )
    )

    context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={"message": "I was charged twice."},
                producer="support-api",
                provenance="support-case-123",
                confidence=1.0,
            ),
        )
    )

    strategy = EventFieldStrategy(
        metadata=StrategyMetadata(
            name="Extract customer message",
            description="Extract the latest customer support message.",
        ),
        event_type="customer.message.received",
        field_name="message",
        output_event_type="customer.message.extracted",
    )

    executor = StrategyExecutor(clock=lambda: next(timestamps))

    result = asyncio.run(executor.execute(strategy, context))

    assert result.output == "I was charged twice."
    assert result.initial_context == context

    assert tuple(event.event_type for event in result.final_context.events) == (
        "customer.message.received",
        "strategy.execution.started",
        "customer.message.extracted",
        "strategy.execution.completed",
    )

    extracted = result.final_context.latest("customer.message.extracted")

    assert extracted is not None
    assert extracted.payload["value"] == "I was charged twice."

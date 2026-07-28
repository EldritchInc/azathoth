"""Tests for strategy execution and lifecycle tracing."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context, ContextEvent
from azathoth.execution import StrategyExecutor
from azathoth.strategies import StrategyMetadata, StrategyOutcome


class RecordingStrategy:
    """A test strategy that records the context it receives."""

    def __init__(self) -> None:
        self.received_context: Context | None = None
        self._metadata = StrategyMetadata(
            id=UUID("bbd0d439-d93a-4dd9-838f-cc23fe93e29a"),
            name="Recording strategy",
            description="Records the context supplied by the executor.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        return self._metadata

    async def run(self, context: Context) -> StrategyOutcome:
        self.received_context = context

        return StrategyOutcome(
            output={"category": "duplicate_charge"},
            events=(
                ContextEvent(
                    event_type="customer.intent.classified",
                    payload={"intent": "duplicate_charge"},
                    producer="recording-strategy",
                    confidence=0.98,
                ),
            ),
        )


def test_executor_records_strategy_lifecycle() -> None:
    timestamps = iter(
        (
            datetime(2026, 7, 28, 14, 0, tzinfo=UTC),
            datetime(2026, 7, 28, 14, 0, 1, tzinfo=UTC),
        )
    )
    executor = StrategyExecutor(clock=lambda: next(timestamps))
    strategy = RecordingStrategy()

    initial_event = ContextEvent(
        event_type="customer.message.received",
        payload={"message": "I was charged twice."},
        producer="test-suite",
    )
    initial_context = Context(events=(initial_event,))

    result = asyncio.run(executor.execute(strategy, initial_context))

    assert result.output == {"category": "duplicate_charge"}
    assert result.initial_context == initial_context
    assert initial_context.events == (initial_event,)

    final_event_types = tuple(event.event_type for event in result.final_context.events)

    assert final_event_types == (
        "customer.message.received",
        "strategy.execution.started",
        "customer.intent.classified",
        "strategy.execution.completed",
    )


def test_strategy_receives_context_containing_started_event() -> None:
    timestamps = iter(
        (
            datetime(2026, 7, 28, 14, 0, tzinfo=UTC),
            datetime(2026, 7, 28, 14, 0, 1, tzinfo=UTC),
        )
    )
    executor = StrategyExecutor(clock=lambda: next(timestamps))
    strategy = RecordingStrategy()

    asyncio.run(executor.execute(strategy, Context()))

    assert strategy.received_context is not None
    assert strategy.received_context.latest("strategy.execution.started") is not None


def test_executor_records_strategy_identity() -> None:
    timestamps = iter(
        (
            datetime(2026, 7, 28, 14, 0, tzinfo=UTC),
            datetime(2026, 7, 28, 14, 0, 1, tzinfo=UTC),
        )
    )
    executor = StrategyExecutor(clock=lambda: next(timestamps))
    strategy = RecordingStrategy()

    result = asyncio.run(executor.execute(strategy, Context()))

    assert result.strategy_id == strategy.metadata.id
    assert result.strategy_name == "Recording strategy"
    assert result.strategy_version == "1.0.0"

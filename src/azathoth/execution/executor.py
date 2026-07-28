"""Execution services for running strategies against structured context."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeAlias

from azathoth.context import Context, ContextEvent
from azathoth.execution.models import ExecutionResult
from azathoth.strategies import Strategy

Clock: TypeAlias = Callable[[], datetime]


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class StrategyExecutor:
    """Execute strategies while recording consistent lifecycle events."""

    def __init__(self, clock: Clock = utc_now) -> None:
        self._clock = clock

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Execute a strategy and return its output and traceable context."""

        started_at = self._clock()
        metadata = strategy.metadata

        started_event = ContextEvent(
            event_type="strategy.execution.started",
            payload={
                "strategy_id": str(metadata.id),
                "strategy_name": metadata.name,
                "strategy_version": metadata.version,
            },
            producer="strategy-executor",
            occurred_at=started_at,
        )

        execution_context = context.append(started_event)
        outcome = await strategy.run(execution_context)

        for event in outcome.events:
            execution_context = execution_context.append(event)

        completed_at = self._clock()

        completed_event = ContextEvent(
            event_type="strategy.execution.completed",
            payload={
                "strategy_id": str(metadata.id),
                "strategy_name": metadata.name,
                "strategy_version": metadata.version,
            },
            producer="strategy-executor",
            occurred_at=completed_at,
        )

        final_context = execution_context.append(completed_event)

        return ExecutionResult(
            strategy_id=metadata.id,
            strategy_name=metadata.name,
            strategy_version=metadata.version,
            output=outcome.output,
            initial_context=context,
            final_context=final_context,
            started_at=started_at,
            completed_at=completed_at,
        )

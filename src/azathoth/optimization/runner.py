"""Orchestration services for executing and evaluating strategies."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol, TypeAlias

from azathoth.context import Context
from azathoth.evaluation import Evaluator
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.optimization.models import (
    OptimizationExample,
    OptimizationRun,
)
from azathoth.strategies import Strategy

Clock: TypeAlias = Callable[[], datetime]


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class StrategyExecutionService(Protocol):
    """A service capable of executing an Azathoth strategy."""

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Execute a strategy against context."""

        ...


class OptimizationRunner:
    """Execute and evaluate one strategy against one optimization example."""

    def __init__(
        self,
        executor: StrategyExecutionService | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._executor: StrategyExecutionService = (
            executor if executor is not None else StrategyExecutor()
        )
        self._clock = clock

    async def run(
        self,
        example: OptimizationExample,
        strategy: Strategy,
        evaluator: Evaluator,
    ) -> OptimizationRun:
        """Execute and evaluate a strategy against a reproducible example."""

        started_at = self._clock()

        execution = await self._executor.execute(
            strategy=strategy,
            context=example.context,
        )

        evaluation = await evaluator.evaluate(
            expected=example.expected_outcome,
            actual=execution.output,
        )

        completed_at = self._clock()

        return OptimizationRun(
            example_id=example.id,
            execution=execution,
            evaluation=evaluation,
            started_at=started_at,
            completed_at=completed_at,
        )

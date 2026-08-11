"""Tests for workflow retry execution."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    WorkflowRetryPolicy,
    WorkflowRunner,
)

STRATEGY_ID = UUID("f4638acb-ec75-42fb-a5d1-f94734b51b77")


class StubStrategy:
    """A deterministic executable strategy."""

    def __init__(self) -> None:
        self._metadata = StrategyMetadata(
            id=STRATEGY_ID,
            name="Retry",
            description="Retry",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return self._metadata

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Return a placeholder outcome."""

        return StrategyOutcome(
            output="unused",
        )


class FlakyExecutor(StrategyExecutor):
    """Fail a configured number of executions."""

    def __init__(
        self,
        *,
        failures: int,
    ) -> None:
        self.remaining_failures = failures
        self.calls = 0

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Fail until the configured failures are exhausted."""

        self.calls += 1

        if self.remaining_failures > 0:
            self.remaining_failures -= 1

            raise RuntimeError("boom")

        now = datetime(
            2026,
            8,
            11,
            tzinfo=UTC,
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output="ok",
            initial_context=context,
            final_context=context,
            started_at=now,
            completed_at=now,
        )


def create_runner(
    failures: int,
) -> tuple[
    WorkflowRunner,
    FlakyExecutor,
]:
    """Create a runner with a flaky executor."""

    executor = FlakyExecutor(
        failures=failures,
    )

    return (
        WorkflowRunner(
            executor=executor,
        ),
        executor,
    )


def test_retry_succeeds_after_second_attempt() -> None:
    runner, executor = create_runner(1)

    execution, attempts, error = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(
                max_attempts=2,
            ),
        )
    )

    assert error is None
    assert execution is not None
    assert execution.output == "ok"

    assert executor.calls == 2
    assert len(attempts) == 2


def test_retry_succeeds_after_third_attempt() -> None:
    runner, executor = create_runner(2)

    execution, attempts, error = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(
                max_attempts=3,
            ),
        )
    )

    assert error is None
    assert execution is not None

    assert executor.calls == 3

    assert tuple(attempt.succeeded for attempt in attempts) == (
        False,
        False,
        True,
    )


def test_retry_exhaustion_returns_failure_and_attempt_history() -> None:
    runner, executor = create_runner(3)

    execution, attempts, error = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(
                max_attempts=3,
            ),
        )
    )

    assert execution is None

    assert isinstance(
        error,
        RuntimeError,
    )
    assert str(error) == "boom"

    assert executor.calls == 3
    assert len(attempts) == 3

    assert all(not attempt.succeeded for attempt in attempts)


def test_single_attempt_success_does_not_retry() -> None:
    runner, executor = create_runner(0)

    execution, attempts, error = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(),
        )
    )

    assert error is None
    assert execution is not None

    assert executor.calls == 1
    assert len(attempts) == 1

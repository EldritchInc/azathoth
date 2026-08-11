"""Tests for workflow retry execution."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

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

STRATEGY_ID = UUID("ba6e8918-5ec7-4af4-a851-4bd70838853d")


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
        """Return stable strategy metadata."""

        return self._metadata

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Return a deterministic placeholder outcome."""

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
        """Fail until the configured number of failures is exhausted."""

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
) -> tuple[WorkflowRunner, FlakyExecutor]:
    """Create a workflow runner backed by a flaky executor."""

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

    result, _attempts = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(
                max_attempts=2,
            ),
        )
    )

    assert result.output == "ok"
    assert executor.calls == 2


def test_retry_succeeds_after_third_attempt() -> None:
    runner, executor = create_runner(2)

    result, _attempts = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(
                max_attempts=3,
            ),
        )
    )

    assert result.output == "ok"
    assert executor.calls == 3


def test_retry_exhausts_attempts() -> None:
    runner, executor = create_runner(3)

    with pytest.raises(
        RuntimeError,
        match="boom",
    ):
        asyncio.run(
            runner._execute_with_retry(
                strategy=StubStrategy(),
                context=Context(),
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=3,
                ),
            )
        )

    assert executor.calls == 3


def test_single_attempt_does_not_retry() -> None:
    runner, executor = create_runner(0)

    result, _attempts = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(),
        )
    )

    assert result.output == "ok"
    assert executor.calls == 1


def test_single_attempt_failure_is_propagated() -> None:
    runner, executor = create_runner(1)

    with pytest.raises(
        RuntimeError,
        match="boom",
    ):
        asyncio.run(
            runner._execute_with_retry(
                strategy=StubStrategy(),
                context=Context(),
                retry_policy=WorkflowRetryPolicy(),
            )
        )

    assert executor.calls == 1

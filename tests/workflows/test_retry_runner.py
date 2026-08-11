"""Tests for retry behavior through WorkflowRunner."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import Strategy, StrategyMetadata, StrategyOutcome
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRunner,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("78c7d004-5864-47df-95c2-5d48b6a040f6")
STEP_ID = UUID("0dcf90d6-f866-4d17-bf8a-dbf64cf37df4")
STRATEGY_ID = UUID("fd17dc29-b9bf-448f-a758-c5f73a0a37fb")


class StubStrategy:
    """A deterministic executable strategy."""

    def __init__(self) -> None:
        self._metadata = StrategyMetadata(
            id=STRATEGY_ID,
            name="Retryable step",
            description="A retryable workflow step.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return self._metadata

    async def run(self, context: Context) -> StrategyOutcome:
        """Return a placeholder outcome."""

        return StrategyOutcome(
            output="unused",
        )


class FlakyExecutor(StrategyExecutor):
    """Fail a configured number of times before succeeding."""

    def __init__(
        self,
        *,
        failures_before_success: int,
    ) -> None:
        self._remaining_failures = failures_before_success
        self.calls = 0

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Fail until the configured number of failures is exhausted."""

        self.calls += 1

        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise RuntimeError("temporary failure")

        now = datetime(
            2026,
            8,
            10,
            20,
            0,
            tzinfo=UTC,
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output="success",
            initial_context=context,
            final_context=context,
            started_at=now,
            completed_at=now,
        )


def create_candidate(
    *,
    retry_policy: WorkflowRetryPolicy,
) -> WorkflowCandidate:
    """Create a one-step workflow with the supplied retry policy."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Retry workflow",
            description="Exercise workflow retry behavior.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ID,
                strategy=StubStrategy(),
                retry_policy=retry_policy,
            ),
        ),
    )


def test_runner_succeeds_on_first_attempt_without_retry() -> None:
    executor = FlakyExecutor(
        failures_before_success=0,
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=3,
                ),
            ),
            context=Context(),
        )
    )

    assert executor.calls == 1
    assert len(run.steps) == 1
    assert run.steps[0].status is WorkflowStepStatus.EXECUTED
    assert run.steps[0].execution is not None
    assert run.steps[0].execution.output == "success"


def test_runner_retries_and_succeeds_on_second_attempt() -> None:
    executor = FlakyExecutor(
        failures_before_success=1,
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=2,
                ),
            ),
            context=Context(),
        )
    )

    assert executor.calls == 2
    assert run.steps[0].status is WorkflowStepStatus.EXECUTED
    assert run.steps[0].execution is not None
    assert run.steps[0].execution.output == "success"


def test_runner_retries_and_succeeds_on_third_attempt() -> None:
    executor = FlakyExecutor(
        failures_before_success=2,
    )

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=3,
                ),
            ),
            context=Context(),
        )
    )

    assert executor.calls == 3
    assert run.steps[0].status is WorkflowStepStatus.EXECUTED


def test_runner_propagates_failure_after_retry_exhaustion() -> None:
    executor = FlakyExecutor(
        failures_before_success=3,
    )

    with pytest.raises(
        RuntimeError,
        match="temporary failure",
    ):
        asyncio.run(
            WorkflowRunner(
                executor=executor,
            ).run(
                workflow=create_candidate(
                    retry_policy=WorkflowRetryPolicy(
                        max_attempts=3,
                    ),
                ),
                context=Context(),
            )
        )

    assert executor.calls == 3


def test_default_retry_policy_attempts_only_once() -> None:
    executor = FlakyExecutor(
        failures_before_success=1,
    )

    with pytest.raises(
        RuntimeError,
        match="temporary failure",
    ):
        asyncio.run(
            WorkflowRunner(
                executor=executor,
            ).run(
                workflow=create_candidate(
                    retry_policy=WorkflowRetryPolicy(),
                ),
                context=Context(),
            )
        )

    assert executor.calls == 1

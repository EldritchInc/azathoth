"""Tests for retry delays applied by WorkflowRunner."""

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
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRunner,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("8d6f1c2a-0b7e-4f3a-a1c4-6e2d9b0a7c01")

RETRYING_STEP_ID = UUID("8d6f1c2a-0b7e-4f3a-a1c4-6e2d9b0a7c11")
SIBLING_STEP_ID = UUID("8d6f1c2a-0b7e-4f3a-a1c4-6e2d9b0a7c12")

RETRYING_STRATEGY_ID = UUID("8d6f1c2a-0b7e-4f3a-a1c4-6e2d9b0a7c21")
SIBLING_STRATEGY_ID = UUID("8d6f1c2a-0b7e-4f3a-a1c4-6e2d9b0a7c22")

SIBLING_TIMEOUT_SECONDS = 1.0

EXECUTION_TIME = datetime(
    2026,
    10,
    23,
    12,
    30,
    tzinfo=UTC,
)

BACKOFF_POLICY = WorkflowRetryPolicy(
    max_attempts=4,
    initial_delay_seconds=0.5,
    backoff_multiplier=2.0,
    maximum_delay_seconds=1.5,
)


class NamedStrategy:
    """A strategy identified only by its name."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        name: str,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Execute {name}.",
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
            output=self.metadata.name,
        )


class RetryingExecutor(StrategyExecutor):
    """Fail the retrying strategy a configured number of times."""

    def __init__(
        self,
        *,
        failures_before_success: int,
    ) -> None:
        self._remaining_failures = failures_before_success
        self.calls: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Fail the retrying strategy until its failures are exhausted."""

        self.calls.append(strategy.metadata.name)

        if strategy.metadata.name == "Retrying" and self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise RuntimeError("temporary failure")

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=strategy.metadata.name,
            initial_context=context,
            final_context=context,
            started_at=EXECUTION_TIME,
            completed_at=EXECUTION_TIME,
        )


class RecordingSleep:
    """Record requested retry delays without waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(
        self,
        delay: float,
    ) -> None:
        """Record one requested delay."""

        self.delays.append(delay)


def create_candidate(
    *,
    retry_policy: WorkflowRetryPolicy,
    include_sibling: bool = False,
) -> WorkflowCandidate:
    """Create a workflow whose first step retries under the supplied policy."""

    steps = [
        WorkflowCandidateStep(
            id=RETRYING_STEP_ID,
            strategy=NamedStrategy(
                strategy_id=RETRYING_STRATEGY_ID,
                name="Retrying",
            ),
            retry_policy=retry_policy,
            failure_policy=WorkflowFailurePolicy.CONTINUE,
        ),
    ]

    if include_sibling:
        steps.append(
            WorkflowCandidateStep(
                id=SIBLING_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=SIBLING_STRATEGY_ID,
                    name="Sibling",
                ),
            )
        )

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Retry delay workflow",
            description="Exercise workflow retry delays.",
            version="1.0.0",
        ),
        steps=tuple(steps),
    )


def test_runner_waits_the_policy_delay_before_each_retry() -> None:
    sleep = RecordingSleep()

    run = asyncio.run(
        WorkflowRunner(
            executor=RetryingExecutor(
                failures_before_success=4,
            ),
            sleep=sleep,
        ).run(
            workflow=create_candidate(
                retry_policy=BACKOFF_POLICY,
            ),
            context=Context(),
        )
    )

    assert run.steps[0].status is WorkflowStepStatus.FAILED
    assert len(run.steps[0].attempts) == 4

    assert sleep.delays == [
        0.5,
        1.0,
        1.5,
    ]


def test_runner_does_not_wait_after_a_successful_retry() -> None:
    sleep = RecordingSleep()

    run = asyncio.run(
        WorkflowRunner(
            executor=RetryingExecutor(
                failures_before_success=1,
            ),
            sleep=sleep,
        ).run(
            workflow=create_candidate(
                retry_policy=BACKOFF_POLICY,
            ),
            context=Context(),
        )
    )

    assert run.steps[0].status is WorkflowStepStatus.EXECUTED

    assert sleep.delays == [
        0.5,
    ]


def test_runner_does_not_wait_for_zero_delay_retries() -> None:
    sleep = RecordingSleep()

    asyncio.run(
        WorkflowRunner(
            executor=RetryingExecutor(
                failures_before_success=2,
            ),
            sleep=sleep,
        ).run(
            workflow=create_candidate(
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=3,
                ),
            ),
            context=Context(),
        )
    )

    assert sleep.delays == []


def test_retry_delay_does_not_block_concurrent_siblings() -> None:
    sibling_finished = asyncio.Event()

    executor = RetryingExecutor(
        failures_before_success=1,
    )

    class SiblingCompletionExecutor(StrategyExecutor):
        """Signal when the sibling step completes."""

        async def execute(
            self,
            strategy: Strategy,
            context: Context,
        ) -> ExecutionResult:
            """Delegate execution and signal sibling completion."""

            result = await executor.execute(
                strategy,
                context,
            )

            if strategy.metadata.name == "Sibling":
                sibling_finished.set()

            return result

    async def wait_for_sibling(
        delay: float,
    ) -> None:
        """Hold the retry until the sibling has finished."""

        await asyncio.wait_for(
            sibling_finished.wait(),
            timeout=SIBLING_TIMEOUT_SECONDS,
        )

    run = asyncio.run(
        WorkflowRunner(
            executor=SiblingCompletionExecutor(),
            sleep=wait_for_sibling,
        ).run(
            workflow=create_candidate(
                retry_policy=BACKOFF_POLICY,
                include_sibling=True,
            ),
            context=Context(),
        )
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.EXECUTED,
        WorkflowStepStatus.EXECUTED,
    )

    assert executor.calls == [
        "Retrying",
        "Sibling",
        "Retrying",
    ]

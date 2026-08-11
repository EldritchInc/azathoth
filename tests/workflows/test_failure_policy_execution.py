"""Tests for workflow failure policy execution."""

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
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRunner,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("8ac57e8f-3a9c-48a0-ac0f-f8389fd90fb5")

FAILING_STEP_ID = UUID("c4da590c-587c-442e-b23a-bc1827d45adb")
INDEPENDENT_STEP_ID = UUID("4bc8b959-4967-48ec-a02d-394ae04fc516")
DEPENDENT_STEP_ID = UUID("83235da7-75bd-445f-a828-3065af43473d")
GRANDCHILD_STEP_ID = UUID("24737280-0d47-42a8-9443-08d8a86e557c")

FAILING_STRATEGY_ID = UUID("ed5fdc16-a706-4887-84b8-80d188437a7c")
INDEPENDENT_STRATEGY_ID = UUID("b5f94b44-1630-4d0e-8354-af23e2112077")
DEPENDENT_STRATEGY_ID = UUID("cc462058-f11b-4b50-835e-5247c386294b")
GRANDCHILD_STRATEGY_ID = UUID("81e34314-c431-499b-aec4-9ec5c44f26d8")


class StubStrategy:
    """A deterministic workflow strategy."""

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


class SelectiveFailureExecutor(StrategyExecutor):
    """Fail one named strategy and execute all others."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Execute or fail the supplied strategy."""

        self.calls.append(strategy.metadata.name)

        if strategy.metadata.name == "Failing":
            raise RuntimeError("permanent failure")

        now = datetime(
            2026,
            8,
            11,
            12,
            30,
            tzinfo=UTC,
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output=strategy.metadata.name,
            initial_context=context,
            final_context=context,
            started_at=now,
            completed_at=now,
        )


def create_candidate(
    *,
    failure_policy: WorkflowFailurePolicy,
) -> WorkflowCandidate:
    """Create a workflow containing dependent and independent branches."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Failure policy workflow",
            description="Exercise workflow failure policies.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=FAILING_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=FAILING_STRATEGY_ID,
                    name="Failing",
                ),
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=2,
                ),
                failure_policy=failure_policy,
            ),
            WorkflowCandidateStep(
                id=INDEPENDENT_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=INDEPENDENT_STRATEGY_ID,
                    name="Independent",
                ),
            ),
            WorkflowCandidateStep(
                id=DEPENDENT_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=DEPENDENT_STRATEGY_ID,
                    name="Dependent",
                ),
                depends_on=(FAILING_STEP_ID,),
            ),
            WorkflowCandidateStep(
                id=GRANDCHILD_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=GRANDCHILD_STRATEGY_ID,
                    name="Grandchild",
                ),
                depends_on=(DEPENDENT_STEP_ID,),
            ),
        ),
    )


def test_fail_workflow_propagates_original_exception() -> None:
    executor = SelectiveFailureExecutor()

    with pytest.raises(
        RuntimeError,
        match="permanent failure",
    ):
        asyncio.run(
            WorkflowRunner(
                executor=executor,
            ).run(
                workflow=create_candidate(
                    failure_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
                ),
                context=Context(),
            )
        )

    assert executor.calls == [
        "Failing",
        "Failing",
    ]


def test_continue_records_failure_and_runs_downstream_work() -> None:
    executor = SelectiveFailureExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            context=Context(),
        )
    )

    failed = next(step for step in run.steps if step.step_id == FAILING_STEP_ID)

    assert failed.status is WorkflowStepStatus.FAILED
    assert failed.execution is None

    assert len(failed.attempts) == 2
    assert all(not attempt.succeeded for attempt in failed.attempts)

    assert executor.calls == [
        "Failing",
        "Failing",
        "Independent",
        "Dependent",
        "Grandchild",
    ]


def test_skip_dependents_records_failure_and_skips_descendants() -> None:
    executor = SelectiveFailureExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_candidate(
                failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
            ),
            context=Context(),
        )
    )

    statuses = {step.step_id: step.status for step in run.steps}

    assert statuses[FAILING_STEP_ID] is WorkflowStepStatus.FAILED
    assert statuses[INDEPENDENT_STEP_ID] is WorkflowStepStatus.EXECUTED
    assert statuses[DEPENDENT_STEP_ID] is WorkflowStepStatus.SKIPPED
    assert statuses[GRANDCHILD_STEP_ID] is WorkflowStepStatus.SKIPPED

    assert executor.calls == [
        "Failing",
        "Failing",
        "Independent",
    ]


def test_skip_dependents_preserves_declared_workflow_order() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ).run(
            workflow=create_candidate(
                failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
            ),
            context=Context(),
        )
    )

    assert tuple(step.step_id for step in run.steps) == (
        FAILING_STEP_ID,
        INDEPENDENT_STEP_ID,
        DEPENDENT_STEP_ID,
        GRANDCHILD_STEP_ID,
    )


def test_failed_step_preserves_complete_attempt_history() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ).run(
            workflow=create_candidate(
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            context=Context(),
        )
    )

    failed = run.steps[0]

    assert failed.status is WorkflowStepStatus.FAILED

    assert tuple(attempt.attempt_number for attempt in failed.attempts) == (
        1,
        2,
    )

    assert failed.attempts[0].failure is not None
    assert failed.attempts[1].failure is not None

    assert failed.attempts[0].failure.message == "permanent failure"

"""Tests for workflow failure policy boundaries."""

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
    WorkflowCondition,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRun,
    WorkflowRunner,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("4dd33703-b417-453b-8675-52df95e09328")

FAILING_STEP_ID = UUID("6bef9fde-ce4c-484a-89fc-102a44866cf4")
INDEPENDENT_STEP_ID = UUID("28ece72c-fd3d-4660-9189-18d75bbf067b")
DEPENDENT_STEP_ID = UUID("d32db217-f432-433c-bd03-84ec51f81e4b")
INDEPENDENT_CHILD_STEP_ID = UUID("a5848839-c6d3-474a-b01a-2ef14e774c11")
JOIN_STEP_ID = UUID("bc86a88d-5878-4784-a070-49bf56e21864")

FAILING_STRATEGY_ID = UUID("fc698290-eed3-4c6d-b837-ae8f710c4b14")
INDEPENDENT_STRATEGY_ID = UUID("16682322-4f6c-4bea-9898-f0f83ee4dcd8")
DEPENDENT_STRATEGY_ID = UUID("5f170485-4716-485b-aa38-a4e37a779481")
INDEPENDENT_CHILD_STRATEGY_ID = UUID("4316870e-3233-4976-8d51-a39897af9248")
JOIN_STRATEGY_ID = UUID("06700c70-b70e-4b7b-844d-e905dfad284c")


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
        """Return a placeholder strategy outcome."""

        return StrategyOutcome(
            output=self.metadata.name,
        )


class SelectiveFailureExecutor(StrategyExecutor):
    """Fail one strategy while executing every other strategy."""

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

        timestamp = datetime(
            2026,
            8,
            11,
            13,
            0,
            tzinfo=UTC,
        )

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=strategy.metadata.name,
            strategy_version=strategy.metadata.version,
            output={
                "result": strategy.metadata.name,
            },
            initial_context=context,
            final_context=context,
            started_at=timestamp,
            completed_at=timestamp,
        )


def create_continue_candidate() -> WorkflowCandidate:
    """Create a workflow whose failed step allows descendants to continue."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Continue failure workflow",
            description="Continue after an exhausted step failure.",
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
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            WorkflowCandidateStep(
                id=DEPENDENT_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=DEPENDENT_STRATEGY_ID,
                    name="Dependent",
                ),
                depends_on=(FAILING_STEP_ID,),
            ),
        ),
    )


def create_conditional_continue_candidate() -> WorkflowCandidate:
    """Create a downstream condition depending on a failed producer value."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Conditional failure workflow",
            description="Skip when a failed producer has no workflow value.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=FAILING_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=FAILING_STRATEGY_ID,
                    name="Failing",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                        path=("classification",),
                    ),
                ),
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=2,
                ),
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            WorkflowCandidateStep(
                id=DEPENDENT_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=DEPENDENT_STRATEGY_ID,
                    name="Conditional dependent",
                ),
                depends_on=(FAILING_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=FAILING_STEP_ID,
                            name="classification",
                        ),
                        expected="math",
                    ),
                ),
            ),
        ),
    )


def create_skip_dependents_candidate() -> WorkflowCandidate:
    """Create a workflow with failed and independent branches."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Branch isolation workflow",
            description="Skip only descendants of a failed workflow step.",
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
                failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
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
                id=INDEPENDENT_CHILD_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=INDEPENDENT_CHILD_STRATEGY_ID,
                    name="Independent child",
                ),
                depends_on=(INDEPENDENT_STEP_ID,),
            ),
            WorkflowCandidateStep(
                id=JOIN_STEP_ID,
                strategy=StubStrategy(
                    strategy_id=JOIN_STRATEGY_ID,
                    name="Join",
                ),
                depends_on=(
                    DEPENDENT_STEP_ID,
                    INDEPENDENT_CHILD_STEP_ID,
                ),
            ),
        ),
    )


def test_continue_policy_allows_dependency_to_execute() -> None:
    executor = SelectiveFailureExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_continue_candidate(),
            context=Context(),
        )
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.EXECUTED,
    )

    assert executor.calls == [
        "Failing",
        "Failing",
        "Dependent",
    ]


def test_condition_on_missing_failed_output_is_unsatisfied() -> None:
    executor = SelectiveFailureExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_conditional_continue_candidate(),
            context=Context(),
        )
    )

    failing_run = run.steps[0]
    conditional_run = run.steps[1]

    assert failing_run.status is WorkflowStepStatus.FAILED
    assert failing_run.values == ()

    assert conditional_run.status is WorkflowStepStatus.SKIPPED
    assert conditional_run.execution is None
    assert conditional_run.attempts == ()

    assert executor.calls == [
        "Failing",
        "Failing",
    ]


def test_skip_dependents_does_not_poison_independent_branch() -> None:
    executor = SelectiveFailureExecutor()

    run = asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run(
            workflow=create_skip_dependents_candidate(),
            context=Context(),
        )
    )

    statuses = {step.step_id: step.status for step in run.steps}

    assert statuses[FAILING_STEP_ID] is WorkflowStepStatus.FAILED
    assert statuses[DEPENDENT_STEP_ID] is WorkflowStepStatus.SKIPPED

    assert statuses[INDEPENDENT_STEP_ID] is WorkflowStepStatus.EXECUTED
    assert statuses[INDEPENDENT_CHILD_STEP_ID] is WorkflowStepStatus.EXECUTED

    assert statuses[JOIN_STEP_ID] is WorkflowStepStatus.SKIPPED

    assert executor.calls == [
        "Failing",
        "Failing",
        "Independent",
        "Independent child",
    ]


def test_blocked_descendant_chain_propagates_transitively() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ).run(
            workflow=create_skip_dependents_candidate(),
            context=Context(),
        )
    )

    dependent = next(step for step in run.steps if step.step_id == DEPENDENT_STEP_ID)
    join = next(step for step in run.steps if step.step_id == JOIN_STEP_ID)

    assert dependent.status is WorkflowStepStatus.SKIPPED
    assert dependent.attempts == ()

    assert join.status is WorkflowStepStatus.SKIPPED
    assert join.attempts == ()


def test_failed_step_records_all_exhausted_attempts() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ).run(
            workflow=create_continue_candidate(),
            context=Context(),
        )
    )

    failed = run.steps[0]

    assert failed.status is WorkflowStepStatus.FAILED
    assert failed.execution is None
    assert failed.values == ()

    assert tuple(attempt.attempt_number for attempt in failed.attempts) == (
        1,
        2,
    )

    assert tuple(attempt.succeeded for attempt in failed.attempts) == (
        False,
        False,
    )

    for attempt in failed.attempts:
        failure = attempt.failure

        assert failure is not None
        assert failure.exception_type == "RuntimeError"
        assert failure.message == "permanent failure"


def test_failed_workflow_step_round_trips_through_workflow_run_json() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ).run(
            workflow=create_continue_candidate(),
            context=Context(),
        )
    )

    restored = WorkflowRun.model_validate_json(run.model_dump_json())

    assert restored == run

    failed = restored.steps[0]

    assert failed.status is WorkflowStepStatus.FAILED
    assert failed.execution is None
    assert len(failed.attempts) == 2

    assert all(not attempt.succeeded for attempt in failed.attempts)


def test_failure_policy_execution_preserves_declared_step_order() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ).run(
            workflow=create_skip_dependents_candidate(),
            context=Context(),
        )
    )

    assert tuple(step.step_id for step in run.steps) == (
        FAILING_STEP_ID,
        INDEPENDENT_STEP_ID,
        DEPENDENT_STEP_ID,
        INDEPENDENT_CHILD_STEP_ID,
        JOIN_STEP_ID,
    )

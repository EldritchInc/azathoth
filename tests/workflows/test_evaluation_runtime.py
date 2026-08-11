"""Runtime tests for workflow evaluation."""

import asyncio

from azathoth.context import Context
from azathoth.workflows import (
    WorkflowFailurePolicy,
    WorkflowRetryPolicy,
    WorkflowRunner,
)

from .test_failure_policy_execution import (
    SelectiveFailureExecutor,
)
from .test_failure_policy_execution import (
    create_candidate as create_failure_candidate,
)
from .test_retry_runner import (
    FlakyExecutor,
)
from .test_retry_runner import (
    create_candidate as create_retry_candidate,
)


def test_successful_run_evaluation_matches_execution() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=FlakyExecutor(
                failures_before_success=0,
            ),
        ).run(
            workflow=create_retry_candidate(
                retry_policy=WorkflowRetryPolicy(),
            ),
            context=Context(),
        )
    )

    evaluation = run.evaluation

    assert evaluation.workflow_id == run.workflow.id
    assert evaluation.statistics == run.statistics
    assert evaluation.reliability == run.reliability

    assert evaluation.statistics.total_steps == 1
    assert evaluation.statistics.executed_steps == 1
    assert evaluation.statistics.failed_steps == 0
    assert evaluation.statistics.skipped_steps == 0

    assert evaluation.reliability.completion_rate == 1.0
    assert evaluation.reliability.first_attempt_success_rate == 1.0
    assert evaluation.reliability.retry_rate == 0.0
    assert evaluation.reliability.failure_rate == 0.0


def test_retried_run_evaluation_preserves_retry_evidence() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=FlakyExecutor(
                failures_before_success=2,
            ),
        ).run(
            workflow=create_retry_candidate(
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=3,
                ),
            ),
            context=Context(),
        )
    )

    evaluation = run.evaluation

    assert evaluation.statistics.total_attempts == 3
    assert evaluation.statistics.successful_attempts == 1
    assert evaluation.statistics.failed_attempts == 2
    assert evaluation.statistics.retry_count == 2

    assert evaluation.reliability.completion_rate == 1.0
    assert evaluation.reliability.first_attempt_success_rate == 0.0
    assert evaluation.reliability.retry_rate == 1.0
    assert evaluation.reliability.failure_rate == 0.0


def test_failed_run_evaluation_preserves_failure_evidence() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ).run(
            workflow=create_failure_candidate(
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            context=Context(),
        )
    )

    evaluation = run.evaluation

    assert evaluation.workflow_id == run.workflow.id
    assert evaluation.statistics == run.statistics
    assert evaluation.reliability == run.reliability

    assert evaluation.statistics.failed_steps == 1
    assert evaluation.statistics.failed_attempts == 2

    assert evaluation.reliability.failure_rate == 0.25

    assert run.failed
    assert not run.succeeded


def test_skipped_branch_evaluation_preserves_skip_evidence() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ).run(
            workflow=create_failure_candidate(
                failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
            ),
            context=Context(),
        )
    )

    evaluation = run.evaluation

    assert evaluation.statistics.total_steps == 4
    assert evaluation.statistics.executed_steps == 1
    assert evaluation.statistics.failed_steps == 1
    assert evaluation.statistics.skipped_steps == 2

    assert evaluation.reliability.completion_rate == 0.25
    assert evaluation.reliability.first_attempt_success_rate == 0.5
    assert evaluation.reliability.retry_rate == 0.5
    assert evaluation.reliability.failure_rate == 0.5


def test_evaluation_matches_recorded_attempt_history() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=SelectiveFailureExecutor(),
        ).run(
            workflow=create_failure_candidate(
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            context=Context(),
        )
    )

    evaluation = run.evaluation

    assert evaluation.statistics.total_attempts == sum(len(step.attempts) for step in run.steps)

    assert evaluation.statistics.successful_attempts == sum(
        attempt.succeeded for step in run.steps for attempt in step.attempts
    )

    assert evaluation.statistics.failed_attempts == sum(
        not attempt.succeeded for step in run.steps for attempt in step.attempts
    )

    assert evaluation.statistics.retry_count == sum(
        max(
            len(step.attempts) - 1,
            0,
        )
        for step in run.steps
    )


def test_multiple_evaluations_preserve_same_execution_facts() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=FlakyExecutor(
                failures_before_success=1,
            ),
        ).run(
            workflow=create_retry_candidate(
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=2,
                ),
            ),
            context=Context(),
        )
    )

    first = run.evaluation
    second = run.evaluation

    assert first.workflow_id == second.workflow_id
    assert first.statistics == second.statistics
    assert first.reliability == second.reliability

    assert first.statistics == run.statistics
    assert first.reliability == run.reliability

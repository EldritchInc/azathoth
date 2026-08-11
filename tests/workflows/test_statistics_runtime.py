"""Runtime tests for workflow execution statistics."""

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


def test_successful_workflow_statistics() -> None:
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

    statistics = run.statistics

    assert statistics.total_steps == 1
    assert statistics.executed_steps == 1
    assert statistics.failed_steps == 0
    assert statistics.skipped_steps == 0

    assert statistics.total_attempts == 1
    assert statistics.successful_attempts == 1
    assert statistics.failed_attempts == 0

    assert statistics.retry_count == 0

    assert run.succeeded
    assert not run.failed


def test_retried_workflow_statistics() -> None:
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

    statistics = run.statistics

    assert statistics.total_steps == 1
    assert statistics.executed_steps == 1
    assert statistics.failed_steps == 0
    assert statistics.skipped_steps == 0

    assert statistics.total_attempts == 3
    assert statistics.successful_attempts == 1
    assert statistics.failed_attempts == 2

    assert statistics.retry_count == 2

    assert run.retry_count == 2
    assert run.total_attempt_count == 3

    assert run.succeeded
    assert not run.failed


def test_continue_failure_statistics() -> None:
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

    statistics = run.statistics

    assert statistics.total_steps == 4
    assert statistics.executed_steps == 3
    assert statistics.failed_steps == 1
    assert statistics.skipped_steps == 0

    assert statistics.total_attempts == 5
    assert statistics.successful_attempts == 3
    assert statistics.failed_attempts == 2

    assert statistics.retry_count == 1

    assert run.executed_step_count == 3
    assert run.failed_step_count == 1
    assert run.skipped_step_count == 0

    assert run.failed
    assert not run.succeeded


def test_skip_dependents_statistics() -> None:
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

    statistics = run.statistics

    assert statistics.total_steps == 4
    assert statistics.executed_steps == 1
    assert statistics.failed_steps == 1
    assert statistics.skipped_steps == 2

    assert statistics.total_attempts == 3
    assert statistics.successful_attempts == 1
    assert statistics.failed_attempts == 2

    assert statistics.retry_count == 1

    assert run.executed_step_count == 1
    assert run.failed_step_count == 1
    assert run.skipped_step_count == 2

    assert run.failed
    assert not run.succeeded


def test_skipped_steps_do_not_count_as_attempts() -> None:
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

    skipped_steps = tuple(step for step in run.steps if step.status.value == "skipped")

    assert len(skipped_steps) == 2

    assert all(step.attempts == () for step in skipped_steps)

    assert run.statistics.total_attempts == sum(len(step.attempts) for step in run.steps)


def test_statistics_match_recorded_step_history() -> None:
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

    statistics = run.statistics

    assert statistics.total_steps == len(run.steps)

    assert statistics.total_attempts == sum(len(step.attempts) for step in run.steps)

    assert statistics.successful_attempts == sum(
        attempt.succeeded for step in run.steps for attempt in step.attempts
    )

    assert statistics.failed_attempts == sum(
        not attempt.succeeded for step in run.steps for attempt in step.attempts
    )

    assert statistics.retry_count == sum(
        max(
            len(step.attempts) - 1,
            0,
        )
        for step in run.steps
    )


def test_statistics_are_stable_across_repeated_access() -> None:
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

    first = run.statistics
    second = run.statistics

    assert first == second

    assert first.total_attempts == 2
    assert first.retry_count == 1

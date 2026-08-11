"""Tests for persisted workflow execution attempts."""

import asyncio

from azathoth.context import Context
from azathoth.workflows import (
    WorkflowRetryPolicy,
    WorkflowStepStatus,
)
from azathoth.workflows.runner import WorkflowRunner

from .test_retry_runner import (
    FlakyExecutor,
    create_candidate,
)


def test_successful_step_persists_single_attempt() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=FlakyExecutor(
                failures_before_success=0,
            ),
        ).run(
            workflow=create_candidate(
                retry_policy=WorkflowRetryPolicy(),
            ),
            context=Context(),
        )
    )

    step = run.steps[0]

    assert step.status is WorkflowStepStatus.EXECUTED
    assert len(step.attempts) == 1
    assert step.attempts[0].attempt_number == 1
    assert step.attempts[0].succeeded
    assert step.attempts[0].execution == step.execution


def test_retried_step_persists_complete_attempt_history() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=FlakyExecutor(
                failures_before_success=2,
            ),
        ).run(
            workflow=create_candidate(
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=3,
                ),
            ),
            context=Context(),
        )
    )

    step = run.steps[0]

    assert tuple(attempt.attempt_number for attempt in step.attempts) == (
        1,
        2,
        3,
    )

    assert tuple(attempt.succeeded for attempt in step.attempts) == (
        False,
        False,
        True,
    )

    assert step.attempts[0].failure is not None
    assert step.attempts[1].failure is not None
    assert step.attempts[2].execution == step.execution


def test_failed_attempts_preserve_exception_details() -> None:
    run = asyncio.run(
        WorkflowRunner(
            executor=FlakyExecutor(
                failures_before_success=1,
            ),
        ).run(
            workflow=create_candidate(
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=2,
                ),
            ),
            context=Context(),
        )
    )

    failure = run.steps[0].attempts[0].failure

    assert failure is not None
    assert failure.exception_type == "RuntimeError"
    assert failure.message == "temporary failure"

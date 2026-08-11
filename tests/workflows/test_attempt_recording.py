"""Tests for recording workflow execution attempts."""

import asyncio

from azathoth.context import Context
from azathoth.workflows import WorkflowRetryPolicy
from azathoth.workflows.runner import WorkflowRunner

from .test_retry_execution import (
    FlakyExecutor,
    StubStrategy,
)


def test_successful_execution_records_single_attempt() -> None:
    runner = WorkflowRunner(
        executor=FlakyExecutor(
            failures=0,
        ),
    )

    execution, attempts = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(),
        )
    )

    assert execution.output == "ok"

    assert len(attempts) == 1

    attempt = attempts[0]

    assert attempt.attempt_number == 1
    assert attempt.succeeded
    assert attempt.execution == execution
    assert attempt.failure is None


def test_retry_records_failure_then_success() -> None:
    runner = WorkflowRunner(
        executor=FlakyExecutor(
            failures=1,
        ),
    )

    _, attempts = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(
                max_attempts=2,
            ),
        )
    )

    assert len(attempts) == 2

    assert not attempts[0].succeeded
    assert attempts[0].failure is not None

    assert attempts[1].succeeded
    assert attempts[1].execution is not None


def test_retry_numbers_attempts_sequentially() -> None:
    runner = WorkflowRunner(
        executor=FlakyExecutor(
            failures=2,
        ),
    )

    _, attempts = asyncio.run(
        runner._execute_with_retry(
            strategy=StubStrategy(),
            context=Context(),
            retry_policy=WorkflowRetryPolicy(
                max_attempts=3,
            ),
        )
    )

    assert tuple(attempt.attempt_number for attempt in attempts) == (
        1,
        2,
        3,
    )

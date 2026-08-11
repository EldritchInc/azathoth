"""Runtime tests for workflow reliability metrics."""

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


def test_first_attempt_success_has_perfect_reliability() -> None:
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

    reliability = run.reliability

    assert reliability.completion_rate == 1.0
    assert reliability.first_attempt_success_rate == 1.0
    assert reliability.retry_rate == 0.0
    assert reliability.failure_rate == 0.0


def test_recovered_retry_reduces_first_attempt_success_rate() -> None:
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

    reliability = run.reliability

    assert reliability.completion_rate == 1.0
    assert reliability.first_attempt_success_rate == 0.0
    assert reliability.retry_rate == 1.0
    assert reliability.failure_rate == 0.0


def test_permanent_failure_is_reflected_in_reliability() -> None:
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

    reliability = run.reliability

    assert reliability.completion_rate == 0.75
    assert reliability.first_attempt_success_rate == 0.75
    assert reliability.retry_rate == 0.25
    assert reliability.failure_rate == 0.25


def test_skip_dependents_excludes_skipped_steps_from_attempted_rates() -> None:
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

    reliability = run.reliability

    assert reliability.completion_rate == 0.25

    assert reliability.first_attempt_success_rate == 0.5
    assert reliability.retry_rate == 0.5
    assert reliability.failure_rate == 0.5


def test_retry_rate_counts_retried_steps_not_retry_attempts() -> None:
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

    assert run.retry_count == 2

    assert run.reliability.retry_rate == 1.0


def test_reliability_matches_recorded_runtime_history() -> None:
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

    attempted_steps = tuple(step for step in run.steps if step.attempts)

    first_attempt_successes = sum(step.attempts[0].succeeded for step in attempted_steps)

    retried_steps = sum(len(step.attempts) > 1 for step in attempted_steps)

    failed_steps = sum(step.status.value == "failed" for step in attempted_steps)

    reliability = run.reliability

    assert reliability.first_attempt_success_rate == (
        first_attempt_successes / len(attempted_steps)
    )

    assert reliability.retry_rate == (retried_steps / len(attempted_steps))

    assert reliability.failure_rate == (failed_steps / len(attempted_steps))


def test_reliability_is_stable_across_repeated_access() -> None:
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

    assert run.reliability == run.reliability

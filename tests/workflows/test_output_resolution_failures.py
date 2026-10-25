"""Tests for recording unresolvable step outputs as failed attempts."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import Strategy
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRun,
    WorkflowRunner,
    WorkflowStepStatus,
    WorkflowValueBinding,
)
from tests.workflows.test_input_resolution_failures import (
    NamedStrategy,
    require_failure_message,
    step_run,
)

WORKFLOW_ID = UUID("0a7c3e51-2b4d-4e6f-8a1b-3c5d7e9f0b01")

COUNTER_STEP_ID = UUID("0a7c3e51-2b4d-4e6f-8a1b-3c5d7e9f0b11")
REPORTER_STEP_ID = UUID("0a7c3e51-2b4d-4e6f-8a1b-3c5d7e9f0b12")

COUNTER_STRATEGY_ID = UUID("0a7c3e51-2b4d-4e6f-8a1b-3c5d7e9f0b21")
REPORTER_STRATEGY_ID = UUID("0a7c3e51-2b4d-4e6f-8a1b-3c5d7e9f0b22")

SINGLE_ATTEMPT = WorkflowRetryPolicy()

MALFORMED_OUTPUT: JsonValue = {
    "words": 4,
}

WELL_FORMED_OUTPUT: JsonValue = {
    "count": 4,
}

MISSING_KEY_MESSAGE = "Cannot resolve workflow value 'count': missing object key 'count'."

EXECUTION_TIME = datetime(
    2026,
    10,
    25,
    15,
    0,
    tzinfo=UTC,
)


class SequencedOutputExecutor(StrategyExecutor):
    """Answer the counter with a scripted output sequence and everything else plainly.

    The final scripted output repeats once the sequence is exhausted.
    """

    def __init__(
        self,
        counter_outputs: Sequence[JsonValue],
    ) -> None:
        self._counter_outputs = tuple(counter_outputs)
        self.calls: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record the call and return the next scripted output."""

        name = strategy.metadata.name

        counter_calls = sum(1 for call in self.calls if call == "Counter")

        self.calls.append(name)

        output: JsonValue = "reported"

        if name == "Counter":
            output = self._counter_outputs[
                min(
                    counter_calls,
                    len(self._counter_outputs) - 1,
                )
            ]

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=name,
            strategy_version=strategy.metadata.version,
            output=output,
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
        """Record one delay."""

        self.delays.append(delay)


def create_candidate(
    *,
    counter_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.CONTINUE,
    counter_retry_policy: WorkflowRetryPolicy = SINGLE_ATTEMPT,
) -> WorkflowCandidate:
    """Create a counter whose declared output path may be missing, and a reporter after it."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Output resolution failures",
            description="Exercise outputs whose declared path does not resolve.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=COUNTER_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=COUNTER_STRATEGY_ID,
                    name="Counter",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="count",
                        path=("count",),
                    ),
                ),
                retry_policy=counter_retry_policy,
                failure_policy=counter_policy,
            ),
            WorkflowCandidateStep(
                id=REPORTER_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=REPORTER_STRATEGY_ID,
                    name="Reporter",
                ),
                depends_on=(COUNTER_STEP_ID,),
            ),
        ),
    )


def record_run(
    candidate: WorkflowCandidate,
    *,
    executor: SequencedOutputExecutor,
    sleep: RecordingSleep | None = None,
) -> WorkflowRun:
    """Run one candidate, returning its recorded run even when it failed."""

    return asyncio.run(
        WorkflowRunner(
            executor=executor,
            sleep=sleep,
        ).run_recording_failures(
            candidate,
            Context(),
        )
    )


def test_unresolvable_output_fails_the_step_instead_of_crashing() -> None:
    run = record_run(
        create_candidate(),
        executor=SequencedOutputExecutor(
            (MALFORMED_OUTPUT,),
        ),
    )

    counter = step_run(
        run,
        COUNTER_STEP_ID,
    )

    assert counter.status is WorkflowStepStatus.FAILED
    assert counter.execution is None
    assert counter.values == ()
    assert len(counter.attempts) == 1
    assert require_failure_message(counter) == (
        "WorkflowValueResolutionError",
        MISSING_KEY_MESSAGE,
    )


def test_unresolvable_output_is_retried_and_can_succeed() -> None:
    executor = SequencedOutputExecutor(
        (
            MALFORMED_OUTPUT,
            WELL_FORMED_OUTPUT,
        ),
    )

    run = record_run(
        create_candidate(
            counter_retry_policy=WorkflowRetryPolicy(
                max_attempts=3,
            ),
        ),
        executor=executor,
    )

    counter = step_run(
        run,
        COUNTER_STEP_ID,
    )

    assert run.succeeded
    assert counter.status is WorkflowStepStatus.EXECUTED
    assert len(counter.attempts) == 2
    assert executor.calls.count("Counter") == 2

    first_failure = counter.attempts[0].failure

    assert first_failure is not None
    assert first_failure.message == MISSING_KEY_MESSAGE
    assert counter.attempts[1].succeeded
    assert tuple((value.name, value.value) for value in counter.values) == (("count", 4),)


def test_unresolvable_output_exhausts_retries_before_failing() -> None:
    executor = SequencedOutputExecutor(
        (MALFORMED_OUTPUT,),
    )

    run = record_run(
        create_candidate(
            counter_retry_policy=WorkflowRetryPolicy(
                max_attempts=2,
            ),
        ),
        executor=executor,
    )

    counter = step_run(
        run,
        COUNTER_STEP_ID,
    )

    assert counter.status is WorkflowStepStatus.FAILED
    assert len(counter.attempts) == 2
    assert all(not attempt.succeeded for attempt in counter.attempts)
    assert executor.calls.count("Counter") == 2


def test_unresolvable_output_retry_waits_the_policy_delay() -> None:
    sleep = RecordingSleep()

    record_run(
        create_candidate(
            counter_retry_policy=WorkflowRetryPolicy(
                max_attempts=2,
                initial_delay_seconds=0.5,
            ),
        ),
        executor=SequencedOutputExecutor(
            (MALFORMED_OUTPUT,),
        ),
        sleep=sleep,
    )

    assert sleep.delays == [0.5]


def test_fail_workflow_on_unresolvable_output_stops_the_run() -> None:
    executor = SequencedOutputExecutor(
        (MALFORMED_OUTPUT,),
    )

    run = record_run(
        create_candidate(
            counter_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
        ),
        executor=executor,
    )

    assert run.failed
    assert tuple(step.step_id for step in run.steps) == (COUNTER_STEP_ID,)
    assert executor.calls == ["Counter"]


def test_continue_on_unresolvable_output_runs_downstream_steps() -> None:
    executor = SequencedOutputExecutor(
        (MALFORMED_OUTPUT,),
    )

    run = record_run(
        create_candidate(
            counter_policy=WorkflowFailurePolicy.CONTINUE,
        ),
        executor=executor,
    )

    reporter = step_run(
        run,
        REPORTER_STEP_ID,
    )

    assert reporter.status is WorkflowStepStatus.EXECUTED
    assert executor.calls == ["Counter", "Reporter"]


def test_skip_dependents_on_unresolvable_output_skips_downstream_steps() -> None:
    executor = SequencedOutputExecutor(
        (MALFORMED_OUTPUT,),
    )

    run = record_run(
        create_candidate(
            counter_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
        ),
        executor=executor,
    )

    reporter = step_run(
        run,
        REPORTER_STEP_ID,
    )

    assert reporter.status is WorkflowStepStatus.SKIPPED
    assert executor.calls == ["Counter"]


def test_unresolvable_output_failure_round_trips_through_run_json() -> None:
    run = record_run(
        create_candidate(),
        executor=SequencedOutputExecutor(
            (MALFORMED_OUTPUT,),
        ),
    )

    assert WorkflowRun.model_validate_json(run.model_dump_json()) == run


def test_resolvable_output_still_executes_in_one_attempt() -> None:
    executor = SequencedOutputExecutor(
        (WELL_FORMED_OUTPUT,),
    )

    run = record_run(
        create_candidate(
            counter_retry_policy=WorkflowRetryPolicy(
                max_attempts=3,
            ),
        ),
        executor=executor,
    )

    counter = step_run(
        run,
        COUNTER_STEP_ID,
    )

    assert run.succeeded
    assert len(counter.attempts) == 1
    assert executor.calls == ["Counter", "Reporter"]

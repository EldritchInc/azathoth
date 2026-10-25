"""Tests for recording unresolvable step inputs as step failures."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.context import Context, ContextEvent
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    EvaluationStatus,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    RUN_FAILURE_EVALUATOR_NAME,
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowContextReference,
    WorkflowFailurePolicy,
    WorkflowInputBinding,
    WorkflowInputResolutionError,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRun,
    WorkflowRunner,
    WorkflowStepRun,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("f6d4a9b5-7e8c-4ba3-8db4-5e6f7a8b9c01")

PRODUCER_STEP_ID = UUID("f6d4a9b5-7e8c-4ba3-8db4-5e6f7a8b9c11")
CONSUMER_STEP_ID = UUID("f6d4a9b5-7e8c-4ba3-8db4-5e6f7a8b9c12")
DOWNSTREAM_STEP_ID = UUID("f6d4a9b5-7e8c-4ba3-8db4-5e6f7a8b9c13")

PRODUCER_STRATEGY_ID = UUID("f6d4a9b5-7e8c-4ba3-8db4-5e6f7a8b9c21")
CONSUMER_STRATEGY_ID = UUID("f6d4a9b5-7e8c-4ba3-8db4-5e6f7a8b9c22")
DOWNSTREAM_STRATEGY_ID = UUID("f6d4a9b5-7e8c-4ba3-8db4-5e6f7a8b9c23")

DATASET_ID = UUID("f6d4a9b5-7e8c-4ba3-8db4-5e6f7a8b9c31")
CASE_ID = UUID("f6d4a9b5-7e8c-4ba3-8db4-5e6f7a8b9c32")

NO_FAILURES: frozenset[str] = frozenset()

PRODUCER_FAILS = frozenset({"Producer"})

SINGLE_ATTEMPT = WorkflowRetryPolicy()

MISSING_VALUE_MESSAGE = (
    f"Workflow input 'answer' could not resolve value 'answer' from step {PRODUCER_STEP_ID}."
)

MISSING_EVENT_MESSAGE = (
    "Workflow context input 'text' could not resolve event type 'request.received'."
)

MISSING_FIELD_MESSAGE = (
    "Workflow context input 'text' could not resolve field 'input' "
    "from event type 'request.received'."
)

EXECUTION_TIME = datetime(
    2026,
    10,
    23,
    14,
    0,
    tzinfo=UTC,
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


class SelectiveFailureExecutor(StrategyExecutor):
    """Record calls, failing configured strategies and answering otherwise."""

    def __init__(
        self,
        *,
        failing: frozenset[str] = NO_FAILURES,
    ) -> None:
        self._failing = failing
        self.calls: list[str] = []

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Record the call, then answer or fail."""

        name = strategy.metadata.name
        self.calls.append(name)

        if name in self._failing:
            raise RuntimeError(f"{name} failed")

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=name,
            strategy_version=strategy.metadata.version,
            output=f"{name.lower()} answer",
            initial_context=context,
            final_context=context,
            started_at=EXECUTION_TIME,
            completed_at=EXECUTION_TIME,
        )


def create_metadata() -> WorkflowMetadata:
    """Return the shared workflow metadata."""

    return WorkflowMetadata(
        id=WORKFLOW_ID,
        name="Input resolution failures",
        description="Exercise inputs that have no value to bind.",
        version="1.0.0",
    )


def create_value_candidate(
    *,
    consumer_policy: WorkflowFailurePolicy,
    consumer_retry_policy: WorkflowRetryPolicy = SINGLE_ATTEMPT,
) -> WorkflowCandidate:
    """Create a chain whose consumer reads a tolerated producer's value."""

    return WorkflowCandidate(
        metadata=create_metadata(),
        steps=(
            WorkflowCandidateStep(
                id=PRODUCER_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=PRODUCER_STRATEGY_ID,
                    name="Producer",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="answer",
                    ),
                ),
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            ),
            WorkflowCandidateStep(
                id=CONSUMER_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=CONSUMER_STRATEGY_ID,
                    name="Consumer",
                ),
                depends_on=(PRODUCER_STEP_ID,),
                inputs=(
                    WorkflowInputBinding(
                        name="answer",
                        source=WorkflowValueReference(
                            producer_step_id=PRODUCER_STEP_ID,
                            name="answer",
                        ),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="result",
                    ),
                ),
                retry_policy=consumer_retry_policy,
                failure_policy=consumer_policy,
            ),
            WorkflowCandidateStep(
                id=DOWNSTREAM_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=DOWNSTREAM_STRATEGY_ID,
                    name="Downstream",
                ),
                depends_on=(CONSUMER_STEP_ID,),
            ),
        ),
    )


def create_context_candidate() -> WorkflowCandidate:
    """Create a one-step workflow reading a request event from context."""

    return WorkflowCandidate(
        metadata=create_metadata(),
        steps=(
            WorkflowCandidateStep(
                id=CONSUMER_STEP_ID,
                strategy=NamedStrategy(
                    strategy_id=CONSUMER_STRATEGY_ID,
                    name="Consumer",
                ),
                inputs=(
                    WorkflowInputBinding(
                        name="text",
                        source=WorkflowContextReference(
                            event_type="request.received",
                            field_name="input",
                        ),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="result",
                    ),
                ),
            ),
        ),
        result=WorkflowValueReference(
            producer_step_id=CONSUMER_STEP_ID,
            name="result",
        ),
    )


def record_run(
    candidate: WorkflowCandidate,
    *,
    executor: SelectiveFailureExecutor,
    context: Context | None = None,
) -> WorkflowRun:
    """Run one candidate, returning its recorded run even when it failed."""

    return asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run_recording_failures(
            workflow=candidate,
            context=context if context is not None else Context(),
        )
    )


def step_run(
    run: WorkflowRun,
    step_id: UUID,
) -> WorkflowStepRun:
    """Return the recorded run of one step."""

    return next(step for step in run.steps if step.step_id == step_id)


def require_failure_message(
    step: WorkflowStepRun,
) -> tuple[str, str]:
    """Return the exception type and message of a step's final failure."""

    failure = step.attempts[-1].failure

    assert failure is not None

    return (
        failure.exception_type,
        failure.message,
    )


def test_missing_producer_value_fails_the_consumer_instead_of_crashing() -> None:
    run = record_run(
        create_value_candidate(
            consumer_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
        ),
        executor=SelectiveFailureExecutor(
            failing=PRODUCER_FAILS,
        ),
    )

    assert run.failed

    consumer = step_run(run, CONSUMER_STEP_ID)

    assert consumer.status is WorkflowStepStatus.FAILED
    assert consumer.execution is None
    assert consumer.values == ()

    assert require_failure_message(consumer) == (
        "WorkflowInputResolutionError",
        MISSING_VALUE_MESSAGE,
    )


def test_unresolved_consumer_strategy_is_never_executed() -> None:
    executor = SelectiveFailureExecutor(
        failing=PRODUCER_FAILS,
    )

    record_run(
        create_value_candidate(
            consumer_policy=WorkflowFailurePolicy.CONTINUE,
        ),
        executor=executor,
    )

    assert "Consumer" not in executor.calls


def test_unresolved_input_is_not_retried() -> None:
    run = record_run(
        create_value_candidate(
            consumer_policy=WorkflowFailurePolicy.CONTINUE,
            consumer_retry_policy=WorkflowRetryPolicy(
                max_attempts=3,
            ),
        ),
        executor=SelectiveFailureExecutor(
            failing=PRODUCER_FAILS,
        ),
    )

    consumer = step_run(run, CONSUMER_STEP_ID)

    assert tuple(attempt.attempt_number for attempt in consumer.attempts) == (1,)


def test_fail_workflow_on_unresolved_input_stops_the_run() -> None:
    executor = SelectiveFailureExecutor(
        failing=PRODUCER_FAILS,
    )

    run = record_run(
        create_value_candidate(
            consumer_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
        ),
        executor=executor,
    )

    assert tuple(step.step_id for step in run.steps) == (
        PRODUCER_STEP_ID,
        CONSUMER_STEP_ID,
    )

    assert executor.calls == ["Producer"]


def test_fail_workflow_on_unresolved_input_raises_from_run() -> None:
    with pytest.raises(
        WorkflowInputResolutionError,
        match=f"^{MISSING_VALUE_MESSAGE}$",
    ):
        asyncio.run(
            WorkflowRunner(
                executor=SelectiveFailureExecutor(
                    failing=PRODUCER_FAILS,
                ),
            ).run(
                workflow=create_value_candidate(
                    consumer_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
                ),
                context=Context(),
            )
        )


def test_continue_on_unresolved_input_runs_downstream_steps() -> None:
    executor = SelectiveFailureExecutor(
        failing=PRODUCER_FAILS,
    )

    run = record_run(
        create_value_candidate(
            consumer_policy=WorkflowFailurePolicy.CONTINUE,
        ),
        executor=executor,
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.EXECUTED,
    )

    assert executor.calls == [
        "Producer",
        "Downstream",
    ]


def test_skip_dependents_on_unresolved_input_skips_downstream_steps() -> None:
    executor = SelectiveFailureExecutor(
        failing=PRODUCER_FAILS,
    )

    run = record_run(
        create_value_candidate(
            consumer_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
        ),
        executor=executor,
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.SKIPPED,
    )

    assert executor.calls == ["Producer"]


def test_resolved_input_still_executes_normally() -> None:
    run = record_run(
        create_value_candidate(
            consumer_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
        ),
        executor=SelectiveFailureExecutor(),
    )

    assert run.succeeded

    assert all(step.status is WorkflowStepStatus.EXECUTED for step in run.steps)


def test_missing_context_event_fails_the_step() -> None:
    run = record_run(
        create_context_candidate(),
        executor=SelectiveFailureExecutor(),
    )

    assert require_failure_message(run.steps[0]) == (
        "WorkflowInputResolutionError",
        MISSING_EVENT_MESSAGE,
    )


def test_missing_context_field_fails_the_step() -> None:
    run = record_run(
        create_context_candidate(),
        executor=SelectiveFailureExecutor(),
        context=Context(
            events=(
                ContextEvent(
                    event_type="request.received",
                    payload={
                        "other": "one two three",
                    },
                    producer="request-api",
                ),
            )
        ),
    )

    assert require_failure_message(run.steps[0]) == (
        "WorkflowInputResolutionError",
        MISSING_FIELD_MESSAGE,
    )


def test_unresolved_input_failure_round_trips_through_run_json() -> None:
    run = record_run(
        create_context_candidate(),
        executor=SelectiveFailureExecutor(),
    )

    assert WorkflowRun.model_validate_json(run.model_dump_json()) == run


def test_benchmark_scores_unresolved_input_as_a_run_failure() -> None:
    dataset = BenchmarkDataset(
        id=DATASET_ID,
        name="unresolved-input",
        description="Benchmark a workflow reading an event the case never supplies.",
        cases=(
            BenchmarkCase(
                id=CASE_ID,
                input="one two three",
                expected=ExpectedOutcome(
                    description="The consumer answer.",
                    value="consumer answer",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )

    result = asyncio.run(
        WorkflowBenchmarkRunner(
            runner=WorkflowRunner(
                executor=SelectiveFailureExecutor(),
            ),
        ).run(
            dataset,
            lambda case: create_context_candidate(),
        )
    )

    evaluation = result.cases[0].evaluation

    assert evaluation.evaluator_name == RUN_FAILURE_EVALUATOR_NAME
    assert evaluation.status is EvaluationStatus.FAILED
    assert evaluation.reason == (
        f"Workflow run failed at step {CONSUMER_STEP_ID}: {MISSING_EVENT_MESSAGE}"
    )

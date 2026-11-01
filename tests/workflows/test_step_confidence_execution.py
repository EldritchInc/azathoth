"""Tests for recording step confidence while running workflows (ADR 0098)."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context, ContextEvent
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
    WorkflowConditionOperator,
    WorkflowFailurePolicy,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowNamedValueReference,
    WorkflowRetryPolicy,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunner,
    WorkflowStepFinished,
    WorkflowStepRun,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b01")

CLASSIFY_STEP_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b11")
ESCALATE_STEP_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b12")
ROUTE_STEP_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b13")

EXECUTION_TIME = datetime(2026, 10, 31, 21, 30, tzinfo=UTC)

CLASSIFIED_EVENT_TYPE = "ticket.classified"

CLASSIFIER_OUTPUTS = (
    WorkflowValueBinding(name="category", path=("category",)),
    WorkflowValueBinding(name="confidence", path=("confidence",)),
)

CATEGORY_OUTPUT = (WorkflowValueBinding(name="category", path=("category",)),)


class NamedStrategy:
    """A strategy identified only by its name; the executor decides its output."""

    def __init__(
        self,
        name: str,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=UUID(int=sum(name.encode())),
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

        return StrategyOutcome(output=self.metadata.name)


class ScriptedExecutor(StrategyExecutor):
    """Answer each strategy with its scripted outputs in turn, repeating the last.

    Every answer adds one event to the context, so tests can see which events
    carry a confidence. Bound inputs are recorded per strategy.
    """

    def __init__(
        self,
        replies: dict[str, list[JsonValue]],
    ) -> None:
        self._replies = replies
        self.calls: dict[str, int] = {}
        self.bound_inputs: dict[str, list[dict[str, JsonValue]]] = {}

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Answer with the next scripted output."""

        name = strategy.metadata.name
        count = self.calls.get(name, 0)
        self.calls[name] = count + 1

        self.bound_inputs[name] = [
            dict(event.payload)
            for event in context.events
            if event.event_type == "workflow.input.bound"
        ]

        default: list[JsonValue] = [{"routed": True}]
        replies = self._replies.get(name, default)
        output = replies[min(count, len(replies) - 1)]

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=name,
            strategy_version=strategy.metadata.version,
            output=output,
            initial_context=context,
            final_context=context.append(
                ContextEvent(
                    event_type=CLASSIFIED_EVENT_TYPE,
                    payload={"by": name},
                    producer=name,
                ),
            ),
            started_at=EXECUTION_TIME,
            completed_at=EXECUTION_TIME,
        )


class Recorder:
    """Keep every live run event."""

    def __init__(
        self,
    ) -> None:
        self.events: list[WorkflowRunEvent] = []

    def observe(
        self,
        event: WorkflowRunEvent,
    ) -> None:
        self.events.append(event)


def classifier_step(
    *,
    confidence: str | None = "confidence",
    max_attempts: int = 1,
    failure_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.FAIL_WORKFLOW,
) -> WorkflowCandidateStep:
    """Create the cheap classifier, which reports its confidence."""

    return WorkflowCandidateStep(
        id=CLASSIFY_STEP_ID,
        strategy=NamedStrategy("Classify"),
        outputs=CLASSIFIER_OUTPUTS,
        retry_policy=WorkflowRetryPolicy(max_attempts=max_attempts),
        failure_policy=failure_policy,
        confidence=confidence,
    )


def escalating_candidate(
    *,
    threshold: float = 0.8,
) -> WorkflowCandidate:
    """Create a classifier backed by an escalation step, and a step reading the category.

    The escalation step is declared first, so its category is the one read by
    name whenever it ran (ADR 0080).
    """

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Escalating classifier",
            description="Classify cheaply, and escalate when unsure.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=ESCALATE_STEP_ID,
                strategy=NamedStrategy("Escalate"),
                depends_on=(CLASSIFY_STEP_ID,),
                outputs=CATEGORY_OUTPUT,
                conditions=(
                    WorkflowCondition(
                        source=WorkflowValueReference(
                            producer_step_id=CLASSIFY_STEP_ID,
                            name="confidence",
                        ),
                        operator=WorkflowConditionOperator.LESS_THAN,
                        expected=threshold,
                    ),
                ),
            ),
            classifier_step(),
            WorkflowCandidateStep(
                id=ROUTE_STEP_ID,
                strategy=NamedStrategy("Route"),
                depends_on=(ESCALATE_STEP_ID, CLASSIFY_STEP_ID),
                inputs=(
                    WorkflowInputBinding(
                        name="category",
                        source=WorkflowNamedValueReference(name="category"),
                    ),
                ),
            ),
        ),
    )


def single_step_candidate(
    step: WorkflowCandidateStep,
) -> WorkflowCandidate:
    """Create a workflow of one step."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Classifier",
            description="Classify.",
            version="1.0.0",
        ),
        steps=(step,),
    )


def run(
    executor: ScriptedExecutor,
    candidate: WorkflowCandidate,
    observer: Recorder | None = None,
) -> WorkflowRun:
    """Run one candidate, recording failures rather than raising them."""

    return asyncio.run(
        WorkflowRunner(
            executor=executor,
            observer=observer,
        ).run_recording_failures(
            workflow=candidate,
            context=Context(),
        )
    )


def step_run(
    run_record: WorkflowRun,
    step_id: UUID,
) -> WorkflowStepRun:
    """Return one step's run."""

    return next(step for step in run_record.steps if step.step_id == step_id)


def classifier_replies(
    *outputs: JsonValue,
) -> ScriptedExecutor:
    """Script the classifier's replies, and a stronger escalation answer."""

    return ScriptedExecutor(
        {
            "Classify": list(outputs),
            "Escalate": [{"category": "billing"}],
        }
    )


# Recording


@pytest.mark.parametrize("confidence", [0, 0.0, 0.5, 0.95, 1, 1.0])
def test_a_step_records_the_confidence_it_reports(
    confidence: float,
) -> None:
    executor = classifier_replies({"category": "technical", "confidence": confidence})

    run_record = run(executor, single_step_candidate(classifier_step()))

    classify = step_run(run_record, CLASSIFY_STEP_ID)

    assert classify.status is WorkflowStepStatus.EXECUTED
    assert classify.confidence == float(confidence)


def test_a_step_without_a_declared_confidence_records_none() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 2})

    run_record = run(executor, single_step_candidate(classifier_step(confidence=None)))

    classify = step_run(run_record, CLASSIFY_STEP_ID)

    assert classify.status is WorkflowStepStatus.EXECUTED
    assert classify.confidence is None


def test_the_events_a_step_adds_carry_its_confidence() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 0.9})

    run_record = run(executor, single_step_candidate(classifier_step()))

    classified = [
        event
        for event in run_record.final_context.events
        if event.event_type == CLASSIFIED_EVENT_TYPE
    ]

    assert [event.confidence for event in classified] == [0.9]


def test_the_events_of_a_step_without_confidence_carry_none() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 0.9})

    run_record = run(executor, single_step_candidate(classifier_step(confidence=None)))

    assert all(event.confidence is None for event in run_record.final_context.events)


def test_the_finished_event_carries_the_confidence() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 0.9})
    recorder = Recorder()

    run(executor, single_step_candidate(classifier_step()), recorder)

    finished = [event for event in recorder.events if isinstance(event, WorkflowStepFinished)]

    assert [event.confidence for event in finished] == [0.9]


# Invalid confidence


@pytest.mark.parametrize(
    "confidence",
    [1.5, -0.1, 62, "0.9", True, None, [0.9]],
)
def test_an_invalid_confidence_fails_the_attempt(
    confidence: JsonValue,
) -> None:
    executor = classifier_replies({"category": "technical", "confidence": confidence})

    run_record = run(executor, single_step_candidate(classifier_step()))

    classify = step_run(run_record, CLASSIFY_STEP_ID)

    assert classify.status is WorkflowStepStatus.FAILED
    assert classify.confidence is None

    failure = classify.attempts[-1].failure

    assert failure is not None
    assert failure.exception_type == "WorkflowStepConfidenceError"
    assert failure.message.startswith(
        f"Workflow step {CLASSIFY_STEP_ID} confidence 'confidence' must be a number from 0 to 1"
    )


def test_a_missing_confidence_fails_the_attempt_as_an_unresolvable_output() -> None:
    executor = classifier_replies({"category": "technical"})

    run_record = run(executor, single_step_candidate(classifier_step()))

    failure = step_run(run_record, CLASSIFY_STEP_ID).attempts[-1].failure

    assert failure is not None
    assert failure.exception_type == "WorkflowValueResolutionError"


def test_an_invalid_confidence_is_retried_until_one_is_valid() -> None:
    executor = classifier_replies(
        {"category": "technical", "confidence": "high"},
        {"category": "technical", "confidence": 1.2},
        {"category": "technical", "confidence": 0.7},
    )

    run_record = run(executor, single_step_candidate(classifier_step(max_attempts=3)))

    classify = step_run(run_record, CLASSIFY_STEP_ID)

    assert classify.status is WorkflowStepStatus.EXECUTED
    assert classify.confidence == 0.7
    assert [attempt.succeeded for attempt in classify.attempts] == [False, False, True]
    assert executor.calls["Classify"] == 3


def test_exhausted_retries_fall_to_the_failure_policy() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 3})

    run_record = run(
        executor,
        single_step_candidate(
            classifier_step(
                max_attempts=2,
                failure_policy=WorkflowFailurePolicy.CONTINUE,
            )
        ),
    )

    classify = step_run(run_record, CLASSIFY_STEP_ID)

    assert classify.status is WorkflowStepStatus.FAILED
    assert len(classify.attempts) == 2
    assert run_record.halted is not True


def test_a_failed_confidence_halts_a_workflow_that_fails_on_error() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 3})

    run_record = run(executor, single_step_candidate(classifier_step()))

    assert run_record.halted is True
    assert run_record.halting_step_id == CLASSIFY_STEP_ID


# Escalating when unsure


def test_a_confident_classifier_does_not_escalate() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 0.95})

    run_record = run(executor, escalating_candidate())

    assert step_run(run_record, ESCALATE_STEP_ID).status is WorkflowStepStatus.SKIPPED
    assert step_run(run_record, ESCALATE_STEP_ID).confidence is None
    assert "Escalate" not in executor.calls
    assert executor.bound_inputs["Route"] == [
        {
            "name": "category",
            "value": "technical",
            "producer_step_id": str(CLASSIFY_STEP_ID),
            "source_name": "category",
        }
    ]


def test_an_unsure_classifier_escalates_and_the_escalated_category_wins() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 0.55})

    run_record = run(executor, escalating_candidate())

    assert step_run(run_record, CLASSIFY_STEP_ID).confidence == 0.55
    assert step_run(run_record, ESCALATE_STEP_ID).status is WorkflowStepStatus.EXECUTED
    assert executor.calls["Escalate"] == 1
    assert executor.bound_inputs["Route"] == [
        {
            "name": "category",
            "value": "billing",
            "producer_step_id": str(ESCALATE_STEP_ID),
            "source_name": "category",
        }
    ]


def test_a_confidence_at_the_threshold_does_not_escalate() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 0.8})

    run_record = run(executor, escalating_candidate(threshold=0.8))

    assert step_run(run_record, ESCALATE_STEP_ID).status is WorkflowStepStatus.SKIPPED


def test_the_escalation_step_records_no_confidence_of_its_own() -> None:
    executor = classifier_replies({"category": "technical", "confidence": 0.1})

    run_record = run(executor, escalating_candidate())

    assert step_run(run_record, ESCALATE_STEP_ID).confidence is None

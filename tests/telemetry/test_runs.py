"""Tests for tracing workflow runs and their steps (ADR 0100)."""

import asyncio
from datetime import datetime
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.strategies import Strategy, StrategyExecutionMetrics
from azathoth.telemetry import ATTRIBUTE_KEYS, Telemetry
from azathoth.telemetry.otel import OpenTelemetryTelemetry
from azathoth.telemetry.runs import RUN_FAILED_ERROR_TYPE, traced_run
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunner,
    WorkflowStepFinished,
    WorkflowStepStatus,
    combine_observers,
)
from tests.telemetry.fakes import FakeApiTracer, RecordedSpan, RecordingTelemetry
from tests.workflows.test_step_confidence_execution import (
    CLASSIFY_STEP_ID,
    ESCALATE_STEP_ID,
    ROUTE_STEP_ID,
    WORKFLOW_ID,
    NamedStrategy,
    ScriptedExecutor,
    classifier_step,
    escalating_candidate,
    single_step_candidate,
)

SECRET = "Jane Doe's chart, SSN 078-05-1120"

METRICS = StrategyExecutionMetrics(
    provider="openrouter",
    model="anthropic/claude-haiku",
    prompt_tokens=40,
    completion_tokens=10,
    total_tokens=50,
    latency_ms=12,
    estimated_cost_usd=0.0001,
)

LEFT_STEP_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b21")
RIGHT_STEP_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b22")


class TracingExecutor(ScriptedExecutor):
    """Answer as scripted, with metrics, recording the trace context each strategy ran in."""

    def __init__(
        self,
        replies: dict[str, list[JsonValue]],
        telemetry: Telemetry,
        *,
        delay_seconds: float = 0.0,
    ) -> None:
        super().__init__(replies)
        self._telemetry = telemetry
        self._delay_seconds = delay_seconds
        self.trace_contexts: dict[str, dict[str, str]] = {}

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        self.trace_contexts[strategy.metadata.name] = self._telemetry.trace_context()

        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)

        result = await super().execute(strategy, context)

        return result.model_copy(update={"metrics": METRICS})


def traced(
    telemetry: Telemetry,
    executor: ScriptedExecutor,
    candidate: WorkflowCandidate,
) -> WorkflowRun:
    """Run one candidate inside a run trace, as an entry point does."""

    with traced_run(telemetry, workflow_id=candidate.metadata.id) as trace:
        run = asyncio.run(
            WorkflowRunner(
                executor=executor,
                observer=trace.observer,
            ).run_recording_failures(
                workflow=candidate,
                context=Context(),
            )
        )

        trace.record(run)

    return run


def steps_by_id(
    telemetry: RecordingTelemetry,
) -> dict[str, RecordedSpan]:
    """Return the step spans keyed by step ID."""

    return {
        str(span.attributes["azathoth.step.id"]): span for span in telemetry.named("azathoth.step")
    }


# One run


def test_a_run_is_one_span_with_its_steps_under_it() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor(
        {"Classify": [{"category": "billing", "confidence": 0.95}]},
        telemetry,
    )

    run = traced(telemetry, executor, single_step_candidate(classifier_step()))

    (run_span,) = telemetry.named("azathoth.run")
    (step_span,) = telemetry.named("azathoth.step")

    assert run_span.parent is None
    assert step_span.parent is run_span
    assert run_span.ended and step_span.ended
    assert step_span.end_order is not None and run_span.end_order is not None
    assert step_span.end_order < run_span.end_order

    assert run_span.attributes == {
        "azathoth.workflow.id": str(WORKFLOW_ID),
        "azathoth.run.id": str(run.id),
        "azathoth.run.status": "succeeded",
        "azathoth.run.steps.executed": 1,
        "azathoth.run.steps.failed": 0,
        "azathoth.run.steps.skipped": 0,
    }
    assert run_span.error_type is None


def test_an_executed_step_names_its_strategy_model_cost_and_confidence() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor(
        {"Classify": [{"category": "billing", "confidence": 0.95}]},
        telemetry,
    )

    traced(telemetry, executor, single_step_candidate(classifier_step()))

    (step_span,) = telemetry.named("azathoth.step")

    assert step_span.attributes == {
        "azathoth.step.id": str(CLASSIFY_STEP_ID),
        "azathoth.step.status": "executed",
        "azathoth.step.attempts": 1,
        "azathoth.strategy.name": "Classify",
        "azathoth.step.confidence": 0.95,
        "gen_ai.provider.name": "openrouter",
        "gen_ai.request.model": "anthropic/claude-haiku",
        "gen_ai.usage.input_tokens": 40,
        "gen_ai.usage.output_tokens": 10,
        "azathoth.cost.usd": 0.0001,
    }
    assert step_span.events == []
    assert step_span.error_type is None


def test_a_step_runs_inside_its_own_span() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor(
        {"Classify": [{"category": "billing", "confidence": 0.95}]},
        telemetry,
    )

    traced(telemetry, executor, single_step_candidate(classifier_step()))

    (step_span,) = telemetry.named("azathoth.step")

    assert executor.trace_contexts["Classify"] == telemetry.trace_context(step_span)
    assert telemetry.trace_context() == {}


# Escalation


def test_a_skipped_escalation_is_a_span_of_its_own() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor(
        {"Classify": [{"category": "technical", "confidence": 0.95}]},
        telemetry,
    )

    traced(telemetry, executor, escalating_candidate())

    steps = steps_by_id(telemetry)
    (run_span,) = telemetry.named("azathoth.run")

    escalate = steps[str(ESCALATE_STEP_ID)]

    assert escalate.parent is run_span
    assert escalate.attributes == {
        "azathoth.step.id": str(ESCALATE_STEP_ID),
        "azathoth.step.status": "skipped",
        "azathoth.step.attempts": 0,
        "azathoth.strategy.name": "Escalate",
    }
    assert escalate.ended
    assert run_span.attributes["azathoth.run.steps.skipped"] == 1


def test_an_unsure_classifier_escalates_and_both_steps_are_traced() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor(
        {
            "Classify": [{"category": "technical", "confidence": 0.55}],
            "Escalate": [{"category": "billing"}],
        },
        telemetry,
    )

    traced(telemetry, executor, escalating_candidate())

    steps = steps_by_id(telemetry)

    assert steps[str(CLASSIFY_STEP_ID)].attributes["azathoth.step.confidence"] == 0.55
    assert steps[str(ESCALATE_STEP_ID)].attributes["azathoth.step.status"] == "executed"
    assert "azathoth.step.confidence" not in steps[str(ESCALATE_STEP_ID)].attributes
    assert steps[str(ROUTE_STEP_ID)].attributes["azathoth.step.status"] == "executed"
    (run_span,) = telemetry.named("azathoth.run")

    assert all(span.parent is run_span for span in steps.values())


# Failures


def test_each_failed_attempt_is_an_event_naming_its_type() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor(
        {
            "Classify": [
                {"category": "technical", "confidence": "high"},
                {"category": "technical", "confidence": 0.7},
            ]
        },
        telemetry,
    )

    traced(telemetry, executor, single_step_candidate(classifier_step(max_attempts=2)))

    (step_span,) = telemetry.named("azathoth.step")

    assert step_span.attributes["azathoth.step.status"] == "executed"
    assert step_span.attributes["azathoth.step.attempts"] == 2
    assert step_span.error_type is None
    assert [(event.name, event.attributes) for event in step_span.events] == [
        (
            "azathoth.attempt.failed",
            {"azathoth.attempt.number": 1, "error.type": "WorkflowStepConfidenceError"},
        )
    ]
    assert isinstance(step_span.events[0].timestamp, datetime)


def test_a_failed_step_and_its_run_are_marked_failed_by_type() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor(
        {"Classify": [{"category": "technical", "confidence": 3}]},
        telemetry,
    )

    run = traced(telemetry, executor, single_step_candidate(classifier_step(max_attempts=2)))

    (run_span,) = telemetry.named("azathoth.run")
    (step_span,) = telemetry.named("azathoth.step")

    assert run.halted is True
    assert step_span.attributes["azathoth.step.status"] == "failed"
    assert step_span.attributes["azathoth.step.attempts"] == 2
    assert step_span.error_type == "WorkflowStepConfidenceError"
    assert len(step_span.events) == 2
    assert "gen_ai.request.model" not in step_span.attributes
    assert run_span.attributes["azathoth.run.status"] == "failed"
    assert run_span.error_type == "WorkflowStepConfidenceError"


def test_an_exception_escaping_the_run_marks_its_span_by_type() -> None:
    telemetry = RecordingTelemetry()

    with pytest.raises(RuntimeError), traced_run(telemetry, workflow_id=WORKFLOW_ID):
        raise RuntimeError(SECRET)

    (run_span,) = telemetry.spans

    assert run_span.error_type == "RuntimeError"
    assert run_span.ended
    assert SECRET not in repr(run_span)


def test_a_halted_run_without_a_failed_step_names_a_generic_type() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor({"Classify": [{"category": "x", "confidence": 0.9}]}, telemetry)

    with traced_run(telemetry, workflow_id=WORKFLOW_ID) as trace:
        run = asyncio.run(
            WorkflowRunner(executor=executor).run_recording_failures(
                workflow=single_step_candidate(classifier_step()),
                context=Context(),
            )
        )

        trace.record(run.model_copy(update={"halted": True}))

    (run_span,) = telemetry.named("azathoth.run")

    assert run_span.attributes["azathoth.run.status"] == "failed"
    assert run_span.error_type == RUN_FAILED_ERROR_TYPE


# Concurrency


def concurrent_candidate() -> WorkflowCandidate:
    """Create a workflow of two independent steps sharing one layer."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Concurrent",
            description="Two steps in one layer.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(id=LEFT_STEP_ID, strategy=NamedStrategy("Left")),
            WorkflowCandidateStep(id=RIGHT_STEP_ID, strategy=NamedStrategy("Right")),
        ),
    )


def test_concurrent_steps_share_the_run_span_and_see_their_own_context() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor({}, telemetry, delay_seconds=0.01)

    traced(telemetry, executor, concurrent_candidate())

    steps = steps_by_id(telemetry)
    (run_span,) = telemetry.named("azathoth.run")

    left = steps[str(LEFT_STEP_ID)]
    right = steps[str(RIGHT_STEP_ID)]

    assert left.parent is run_span and right.parent is run_span
    assert executor.trace_contexts["Left"] == telemetry.trace_context(left)
    assert executor.trace_contexts["Right"] == telemetry.trace_context(right)
    assert executor.trace_contexts["Left"] != executor.trace_contexts["Right"]


def test_the_opentelemetry_adapter_traces_concurrent_steps_without_leaking_context() -> None:
    tracer = FakeApiTracer()
    telemetry = OpenTelemetryTelemetry(tracer)
    executor = TracingExecutor({}, telemetry, delay_seconds=0.01)

    traced(telemetry, executor, concurrent_candidate())

    run_span, *step_spans = tracer.spans

    assert run_span.name == "azathoth.run"
    assert run_span.parent is None
    assert [span.name for span in step_spans] == ["azathoth.step", "azathoth.step"]
    assert all(span.parent == run_span.context for span in step_spans)
    assert all(span.ended for span in tracer.spans)
    assert {context["TRACEPARENT"] for context in executor.trace_contexts.values()} == {
        f"00-{span.context.trace_id:032x}-{span.context.span_id:016x}-01" for span in step_spans
    }
    assert telemetry.trace_context() == {}


# Combining observers


def test_tracing_combines_with_another_observer() -> None:
    telemetry = RecordingTelemetry()
    seen: list[WorkflowRunEvent] = []

    class Collector:
        def observe(self, event: WorkflowRunEvent) -> None:
            seen.append(event)

    executor = TracingExecutor({"Classify": [{"category": "x", "confidence": 0.9}]}, telemetry)

    with traced_run(telemetry, workflow_id=WORKFLOW_ID) as trace:
        asyncio.run(
            WorkflowRunner(
                executor=executor,
                observer=combine_observers(trace.observer, Collector()),
            ).run_recording_failures(
                workflow=single_step_candidate(classifier_step()),
                context=Context(),
            )
        )

    assert len(telemetry.named("azathoth.step")) == 1
    assert [type(event).__name__ for event in seen] == [
        "WorkflowStepStarted",
        "WorkflowStepFinished",
    ]


def test_combine_observers_drops_absent_ones() -> None:
    class Collector:
        def observe(self, event: WorkflowRunEvent) -> None:
            return None

    collector = Collector()

    assert combine_observers() is None
    assert combine_observers(None, None) is None
    assert combine_observers(None, collector) is collector


def test_one_failing_observer_never_starves_another() -> None:
    seen: list[WorkflowRunEvent] = []

    class Failing:
        def observe(self, event: WorkflowRunEvent) -> None:
            raise RuntimeError("broken pipe")

    class Collector:
        def observe(self, event: WorkflowRunEvent) -> None:
            seen.append(event)

    combined = combine_observers(Failing(), Collector())

    assert combined is not None

    combined.observe(
        WorkflowStepFinished(
            step=classifier_step(),
            layer_index=0,
            status=WorkflowStepStatus.SKIPPED,
        )
    )

    assert len(seen) == 1


# No content


def test_no_span_carries_content() -> None:
    telemetry = RecordingTelemetry()
    executor = TracingExecutor(
        {
            "Classify": [{"category": SECRET, "confidence": "not sure about " + SECRET}],
        },
        telemetry,
    )

    traced(telemetry, executor, single_step_candidate(classifier_step(max_attempts=2)))

    for span in telemetry.spans:
        assert set(span.attributes) <= ATTRIBUTE_KEYS
        assert SECRET not in repr(span.attributes)

        for event in span.events:
            assert set(event.attributes) <= ATTRIBUTE_KEYS
            assert SECRET not in repr(event.attributes)


def test_step_finished_events_carry_attempts_and_execution() -> None:
    seen: list[WorkflowRunEvent] = []

    class Collector:
        def observe(self, event: WorkflowRunEvent) -> None:
            seen.append(event)

    executor = ScriptedExecutor(
        {"Classify": [{"category": "x", "confidence": "?"}, {"category": "x", "confidence": 1}]}
    )

    asyncio.run(
        WorkflowRunner(executor=executor, observer=Collector()).run_recording_failures(
            workflow=single_step_candidate(classifier_step(max_attempts=2)),
            context=Context(),
        )
    )

    (finished,) = [event for event in seen if isinstance(event, WorkflowStepFinished)]

    assert len(finished.attempts) == 2
    assert finished.execution is not None
    assert finished.execution == finished.attempts[-1].execution

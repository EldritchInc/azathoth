"""Tests for the runner that traces every run it executes (ADR 0100)."""

import asyncio

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.telemetry import NO_TELEMETRY
from azathoth.telemetry.invocations import traced_invocation
from azathoth.telemetry.runs import TracingWorkflowRunner, tracing_runner
from azathoth.workflows import (
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunner,
    WorkflowStepConfidenceError,
)
from tests.telemetry.fakes import RecordingTelemetry
from tests.telemetry.test_runs import TracingExecutor
from tests.workflows.test_step_confidence_execution import (
    WORKFLOW_ID,
    classifier_step,
    single_step_candidate,
)

CONFIDENT: dict[str, list[JsonValue]] = {"Classify": [{"category": "billing", "confidence": 0.9}]}


class Collector:
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


def test_without_tracing_the_runner_is_a_plain_one() -> None:
    collector = Collector()

    runner = tracing_runner(NO_TELEMETRY, observer=collector)

    assert type(runner) is WorkflowRunner


def test_with_tracing_the_runner_traces() -> None:
    assert isinstance(tracing_runner(RecordingTelemetry()), TracingWorkflowRunner)


def test_a_traced_run_is_recorded_and_still_observed() -> None:
    telemetry = RecordingTelemetry()
    collector = Collector()

    runner = TracingWorkflowRunner(
        telemetry,
        executor=TracingExecutor(CONFIDENT, telemetry),
        observer=collector,
    )

    run = asyncio.run(
        runner.run_recording_failures(single_step_candidate(classifier_step()), Context())
    )

    (run_span,) = telemetry.named("azathoth.run")
    (step_span,) = telemetry.named("azathoth.step")

    assert run.succeeded
    assert run_span.attributes["azathoth.run.id"] == str(run.id)
    assert run_span.attributes["azathoth.workflow.id"] == str(WORKFLOW_ID)
    assert step_span.parent is run_span
    assert [type(event).__name__ for event in collector.events] == [
        "WorkflowStepStarted",
        "WorkflowStepFinished",
    ]


def test_a_propagated_failure_marks_the_run_span_by_type() -> None:
    telemetry = RecordingTelemetry()

    runner = TracingWorkflowRunner(
        telemetry,
        executor=TracingExecutor({"Classify": [{"category": "x", "confidence": 7}]}, telemetry),
    )

    with pytest.raises(WorkflowStepConfidenceError):
        asyncio.run(runner.run(single_step_candidate(classifier_step()), Context()))

    (run_span,) = telemetry.named("azathoth.run")
    (step_span,) = telemetry.named("azathoth.step")

    assert run_span.error_type == "WorkflowStepConfidenceError"
    assert run_span.ended
    assert step_span.error_type == "WorkflowStepConfidenceError"


def test_a_succeeding_run_propagates_nothing_and_is_recorded() -> None:
    telemetry = RecordingTelemetry()

    runner = TracingWorkflowRunner(telemetry, executor=TracingExecutor(CONFIDENT, telemetry))

    run = asyncio.run(runner.run(single_step_candidate(classifier_step()), Context()))

    (run_span,) = telemetry.named("azathoth.run")

    assert run_span.attributes["azathoth.run.id"] == str(run.id)
    assert run_span.error_type is None


def test_concurrent_runs_on_one_runner_never_share_a_trace() -> None:
    telemetry = RecordingTelemetry()

    runner = TracingWorkflowRunner(
        telemetry,
        executor=TracingExecutor(CONFIDENT, telemetry, delay_seconds=0.01),
    )

    async def both() -> list[WorkflowRun]:
        return list(
            await asyncio.gather(
                runner.run_recording_failures(single_step_candidate(classifier_step()), Context()),
                runner.run_recording_failures(single_step_candidate(classifier_step()), Context()),
            )
        )

    runs = asyncio.run(both())

    run_spans = telemetry.named("azathoth.run")
    step_spans = telemetry.named("azathoth.step")

    assert len(run_spans) == 2 and len(step_spans) == 2
    assert {span.attributes["azathoth.run.id"] for span in run_spans} == {
        str(run.id) for run in runs
    }
    assert {id(span.parent) for span in step_spans} == {id(span) for span in run_spans}


def test_a_run_inside_an_invocation_is_traced_under_it() -> None:
    telemetry = RecordingTelemetry()

    with traced_invocation(telemetry, workflow_id=WORKFLOW_ID):
        asyncio.run(
            TracingWorkflowRunner(
                telemetry, executor=TracingExecutor(CONFIDENT, telemetry)
            ).run_recording_failures(single_step_candidate(classifier_step()), Context())
        )

    invocation, run, step = telemetry.spans

    assert invocation.name == "azathoth.invocation"
    assert run.parent is invocation
    assert step.parent is run

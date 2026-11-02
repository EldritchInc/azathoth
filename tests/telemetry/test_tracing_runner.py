"""Tests for the runner that traces every run it executes (ADR 0100)."""

import asyncio
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import Context
from azathoth.telemetry import NO_TELEMETRY
from azathoth.telemetry.invocations import traced_invocation
from azathoth.telemetry.runs import TracingWorkflowRunner, tracing_runner
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunner,
    WorkflowStepConfidenceError,
)
from tests.telemetry.fakes import RecordingTelemetry
from tests.telemetry.test_runs import TracingExecutor
from tests.workflows.test_run_resume import Crash, CrashingJournal
from tests.workflows.test_runner_journal import (
    FIRST_STEP_ID,
    FlakyStrategy,
    candidate,
    rebuilt,
    step,
)
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


# Journaling (ADR 0105)


INVOCATION_ID = UUID("c1300000-0000-4000-8000-000000000001")


@pytest.mark.parametrize("traced", [False, True], ids=["plain", "traced"])
def test_either_runner_journals_each_run_under_its_invocation(
    traced: bool,
) -> None:
    journal = InMemoryRunJournalRepository()

    runner = tracing_runner(RecordingTelemetry() if traced else NO_TELEMETRY, journal=journal)

    assert isinstance(runner, TracingWorkflowRunner) is traced

    for run_method in (runner.run, runner.run_recording_failures):
        run = asyncio.run(
            run_method(
                candidate(step(FIRST_STEP_ID, FlakyStrategy())),
                Context(),
                invocation_id=INVOCATION_ID,
            )
        )

        entries = journal.entries(run.id)

        assert rebuilt(entries) == run
        assert {entry.invocation_id for entry in entries} == {INVOCATION_ID}


def test_a_traced_resume_is_traced_as_a_run_of_its_workflow() -> None:
    telemetry = RecordingTelemetry()
    journal = CrashingJournal()
    journal.crash("attempt.finished")
    workflow = candidate(step(FIRST_STEP_ID, FlakyStrategy()))

    with pytest.raises(Crash):
        asyncio.run(WorkflowRunner(journal=journal).run(workflow, Context()))

    (run_id,) = journal.run_ids

    run = asyncio.run(tracing_runner(telemetry, journal=journal).resume(workflow, run_id=run_id))

    (run_span,) = telemetry.named("azathoth.run")

    assert run.id == run_id
    assert run_span.attributes["azathoth.run.id"] == str(run_id)

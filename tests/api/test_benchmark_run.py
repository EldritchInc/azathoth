"""Contract tests for running and comparing workflows against a benchmark (ADR 0130)."""

import json
from uuid import UUID

import pytest

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import decode_workflow_document
from tests.api.test_runs import COUNT_WORKFLOW_ID, stock, tool_step, workflow

SECOND_WORKFLOW_ID = UUID("c0000000-0000-4000-8000-000000000006")

SECOND_STEP_ID = UUID("c0000000-0000-4000-8000-000000000061")

NO_RESULT_WORKFLOW_ID = UUID("c0000000-0000-4000-8000-000000000007")

NO_RESULT_STEP_ID = UUID("c0000000-0000-4000-8000-000000000071")

MISSING_ID = UUID("00000000-0000-4000-8000-0000000000ff")


def stocked_benchmark(
    instance: api.Azathoth,
    *cases: tuple[str, object, api.CaseComparison],
) -> UUID:
    """Import the word count workflows, and a benchmark of `cases`: input, expected, comparison."""

    stock(instance)
    instance.workflows.import_document(
        workflow(SECOND_WORKFLOW_ID, tool_step(SECOND_STEP_ID, "word_count"))
    )
    created = instance.benchmarks.create("word count", "Count the words.")

    for given, expected, comparison in cases:
        instance.benchmarks.add_case(
            created.benchmark.id,
            input=api.RunInput(payload=given),
            comparison=comparison,
            expected=expected,  # type: ignore[arg-type]
        )

    return created.benchmark.id


def counted(
    instance: api.Azathoth,
) -> UUID:
    """Return a benchmark of one case the workflow counts right and one it cannot."""

    return stocked_benchmark(
        instance,
        ("one two three", 3, "exact"),
        ("four five", 5, "exact"),
    )


#
# Running
#


def test_a_run_judges_every_case_and_is_saved(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    events: list[api.BenchmarkEvent] = []

    execution = instance.benchmarks.run(benchmark_id, COUNT_WORKFLOW_ID, on_event=events.append)

    assert execution.kind == "run"
    assert execution.benchmark_revision == 3
    assert execution.scoring_policy is None
    (candidate,) = execution.candidates
    assert candidate.workflow_id == COUNT_WORKFLOW_ID
    assert (candidate.cases_passed, candidate.cases_run) == (1, 2)
    assert [case.passed for case in candidate.cases] == [True, False]
    assert all(case.reason is not None for case in candidate.cases)
    assert [summary.execution_id for summary in instance.benchmarks.executions(benchmark_id)] == [
        execution.execution_id
    ]
    assert len(instance.runs.list(COUNT_WORKFLOW_ID)) == 2


def test_a_run_tells_each_case_as_it_starts_and_finishes(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    events: list[api.BenchmarkEvent] = []

    execution = instance.benchmarks.run(benchmark_id, COUNT_WORKFLOW_ID, on_event=events.append)

    first, second = execution.candidates[0].cases
    assert [event.type for event in events] == [
        "case_started",
        "case_finished",
        "case_started",
        "case_finished",
    ]
    assert events[0] == api.CaseStarted(
        case_id=first.case_id, workflow_id=COUNT_WORKFLOW_ID, index=1, total=2
    )
    assert events[1] == api.CaseFinished(
        case_id=first.case_id,
        workflow_id=COUNT_WORKFLOW_ID,
        run_id=first.run_id,
        passed=True,
        score=1.0,
    )
    assert isinstance(events[2], api.CaseStarted)
    assert (events[2].case_id, events[2].index) == (second.case_id, 2)
    assert isinstance(events[3], api.CaseFinished)
    assert events[3].passed is False


def test_a_listener_that_raises_never_stops_the_benchmark(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    heard: list[api.BenchmarkEvent] = []

    def broken(
        event: api.BenchmarkEvent,
    ) -> None:
        heard.append(event)
        raise RuntimeError("The listener broke.")

    execution = instance.benchmarks.run(benchmark_id, COUNT_WORKFLOW_ID, on_event=broken)

    assert execution.candidates[0].cases_run == 2
    assert len(heard) == 1


def test_a_cancelled_run_keeps_the_cases_it_ran_and_records_no_execution(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    token = api.CancellationToken()

    def cancel_after_first(
        event: api.BenchmarkEvent,
    ) -> None:
        if isinstance(event, api.CaseFinished):
            token.cancel()

    with pytest.raises(api.RunCancelledError):
        instance.benchmarks.run(
            benchmark_id, COUNT_WORKFLOW_ID, on_event=cancel_after_first, cancel=token
        )

    assert instance.benchmarks.executions(benchmark_id) == ()
    assert len(instance.runs.list(COUNT_WORKFLOW_ID)) == 1


def test_a_run_cancelled_before_it_starts_runs_nothing(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    token = api.CancellationToken()
    token.cancel()

    with pytest.raises(api.RunCancelledError):
        instance.benchmarks.run(benchmark_id, COUNT_WORKFLOW_ID, cancel=token)

    assert instance.runs.list(COUNT_WORKFLOW_ID) == ()


#
# Comparing
#


def test_a_comparison_ranks_every_workflow_and_is_saved(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    events: list[api.BenchmarkEvent] = []

    execution = instance.benchmarks.compare(
        benchmark_id,
        [COUNT_WORKFLOW_ID, SECOND_WORKFLOW_ID],
        target_latency_seconds=5.0,
        target_cost_usd=0.01,
        on_event=events.append,
    )

    assert execution.kind == "compare"
    assert execution.scoring_policy == api.ScoringPolicySummary(
        target_latency_seconds=5.0, target_cost_usd=0.01
    )
    assert {candidate.workflow_id for candidate in execution.candidates} == {
        COUNT_WORKFLOW_ID,
        SECOND_WORKFLOW_ID,
    }
    assert all(candidate.scorecard is not None for candidate in execution.candidates)
    assert len(events) == 8
    assert {event.workflow_id for event in events} == {COUNT_WORKFLOW_ID, SECOND_WORKFLOW_ID}


@pytest.mark.parametrize(
    ("workflow_ids", "latency", "message"),
    [
        ((COUNT_WORKFLOW_ID,), 5.0, "at least two distinct workflows"),
        ((COUNT_WORKFLOW_ID, COUNT_WORKFLOW_ID), 5.0, "at least two distinct workflows"),
        ((COUNT_WORKFLOW_ID, SECOND_WORKFLOW_ID), 0.0, "greater than 0"),
    ],
)
def test_a_comparison_needs_two_workflows_and_positive_targets(
    instance: api.Azathoth,
    workflow_ids: tuple[UUID, ...],
    latency: float,
    message: str,
) -> None:
    benchmark_id = counted(instance)

    with pytest.raises(api.InvalidArgumentError, match=message):
        instance.benchmarks.compare(
            benchmark_id, workflow_ids, target_latency_seconds=latency, target_cost_usd=0.01
        )

    assert instance.runs.list(COUNT_WORKFLOW_ID) == ()


#
# What is refused before any case runs
#


def test_a_benchmark_with_no_cases_is_refused(
    instance: api.Azathoth,
) -> None:
    benchmark_id = stocked_benchmark(instance)

    with pytest.raises(api.InvalidArgumentError, match=f"Benchmark {benchmark_id} has no cases."):
        instance.benchmarks.run(benchmark_id, COUNT_WORKFLOW_ID)


def test_a_semantic_case_with_no_judge_is_refused(
    instance: api.Azathoth,
) -> None:
    benchmark_id = stocked_benchmark(instance, ("one two three", 3, "semantic"))

    with pytest.raises(api.JudgeUnavailableError, match="but no judges are configured") as raised:
        instance.benchmarks.run(benchmark_id, COUNT_WORKFLOW_ID)

    assert raised.value.code == "judge_unavailable"
    assert isinstance(raised.value, api.ConflictError)
    assert instance.runs.list(COUNT_WORKFLOW_ID) == ()


def test_a_workflow_that_declares_no_result_is_refused(
    location: str,
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    document = workflow(NO_RESULT_WORKFLOW_ID, tool_step(NO_RESULT_STEP_ID, "word_count"))
    del document["result"]

    # Importing refuses such a workflow now; one saved before that rule is still kept.
    open_repositories(location).workflows.save(decode_workflow_document(json.dumps(document)))

    with pytest.raises(
        api.InvalidArgumentError,
        match=f"Workflow {NO_RESULT_WORKFLOW_ID} does not declare a result.",
    ):
        instance.benchmarks.run(benchmark_id, NO_RESULT_WORKFLOW_ID)


def test_an_unknown_benchmark_or_workflow_is_not_found(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)

    with pytest.raises(api.NotFoundError, match="is not configured"):
        instance.benchmarks.run(MISSING_ID, COUNT_WORKFLOW_ID)

    with pytest.raises(api.NotFoundError):
        instance.benchmarks.run(benchmark_id, MISSING_ID)

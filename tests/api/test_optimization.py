"""Contract tests for optimizing a workflow against a benchmark, as it runs (ADR 0131)."""

import json
import shlex
from uuid import UUID

import pytest

from azathoth import api
from azathoth.cli.parsing import build_parser
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import decode_workflow_document
from tests.api.test_benchmark_run import (
    MISSING_ID,
    NO_RESULT_STEP_ID,
    NO_RESULT_WORKFLOW_ID,
    counted,
    stocked_benchmark,
)
from tests.api.test_runs import COUNT_WORKFLOW_ID, tool_step, workflow

LATENCY = 5.0

COST = 0.01


def optimized(
    instance: api.Azathoth,
    benchmark_id: UUID,
    *,
    events: list[api.OptimizationEvent] | None = None,
    generations: int = 2,
) -> api.OptimizationSummary:
    """Optimize the word count workflow against a benchmark, hearing every event."""

    return instance.optimization.optimize(
        COUNT_WORKFLOW_ID,
        benchmark_id,
        generations=generations,
        on_event=None if events is None else events.append,
        target_latency_seconds=LATENCY,
        target_cost_usd=COST,
    )


def test_a_session_runs_every_generation_and_records_each_experiment(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)

    summary = optimized(instance, benchmark_id)

    assert (summary.workflow_id, summary.benchmark_id) == (COUNT_WORKFLOW_ID, benchmark_id)
    assert [generation.generation for generation in summary.generations] == [1, 2]
    assert [generation.proposed for generation in summary.generations] == [1, 1]
    assert summary.final_experiment_id is None
    assert summary.final_skipped == (
        "Generation 2 proposed no new candidates, so its winner is the session's winner."
    )
    assert summary.winning_experiment_id == summary.generations[-1].experiment_id
    assert (summary.judge_calls, summary.judge_cost_usd) == (0, 0.0)
    assert {
        experiment.experiment_id for experiment in instance.experiments.list(COUNT_WORKFLOW_ID)
    } == {generation.experiment_id for generation in summary.generations}
    words = shlex.split(summary.command)
    assert words[:3] == ["azathoth", "experiment", "show"]
    build_parser().parse_args(words[1:])


def test_a_generations_winner_is_the_experiments_winner(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)

    summary = optimized(instance, benchmark_id, generations=1)
    (only,) = summary.generations
    detail = instance.experiments.get(only.experiment_id)

    assert only.winner_strategy_ids == detail.candidates[0].strategy_ids
    assert only.winner_score == pytest.approx(detail.candidates[0].scorecard.overall_score)
    assert detail.benchmark_id == benchmark_id
    assert (detail.candidates[0].cases_run, detail.candidates[0].cases_passed) == (2, 1)


def test_a_session_tells_each_generation_and_candidate_as_it_goes(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    events: list[api.OptimizationEvent] = []

    summary = optimized(instance, benchmark_id, events=events)

    assert [event.type for event in events] == [
        "generation_started",
        "candidate_finished",
        "generation_finished",
        "generation_started",
        "candidate_finished",
        "generation_finished",
    ]
    assert events[0] == api.GenerationStarted(generation=1, candidates=1, final=False)
    finished = events[1]
    assert isinstance(finished, api.CandidateFinished)
    assert (finished.generation, finished.workflow_id) == (1, COUNT_WORKFLOW_ID)
    assert (finished.cases_run, finished.cases_passed) == (2, 1)
    assert finished.strategy_ids == summary.generations[0].winner_strategy_ids
    assert events[2] == api.GenerationFinished(
        generation=1,
        experiment_id=summary.generations[0].experiment_id,
        winner_strategy_ids=summary.generations[0].winner_strategy_ids,
        winner_score=summary.generations[0].winner_score,
        proposed=1,
    )


def test_a_listener_that_raises_never_stops_the_session(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    heard: list[api.OptimizationEvent] = []

    def broken(
        event: api.OptimizationEvent,
    ) -> None:
        heard.append(event)
        raise RuntimeError("The listener broke.")

    summary = instance.optimization.optimize(
        COUNT_WORKFLOW_ID,
        benchmark_id,
        generations=2,
        on_event=broken,
        target_latency_seconds=LATENCY,
        target_cost_usd=COST,
    )

    assert len(summary.generations) == 2
    assert len(heard) == 1


def test_a_cancelled_session_keeps_the_experiments_it_finished(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    token = api.CancellationToken()

    def cancel_after_first_generation(
        event: api.OptimizationEvent,
    ) -> None:
        if isinstance(event, api.GenerationFinished):
            token.cancel()

    with pytest.raises(api.RunCancelledError):
        instance.optimization.optimize(
            COUNT_WORKFLOW_ID,
            benchmark_id,
            generations=3,
            on_event=cancel_after_first_generation,
            cancel=token,
            target_latency_seconds=LATENCY,
            target_cost_usd=COST,
        )

    assert len(instance.experiments.list(COUNT_WORKFLOW_ID)) == 1
    assert len(instance.runs.list(COUNT_WORKFLOW_ID)) == 2


def test_a_session_cancelled_before_it_starts_runs_nothing(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    token = api.CancellationToken()
    token.cancel()

    with pytest.raises(api.RunCancelledError):
        instance.optimization.optimize(
            COUNT_WORKFLOW_ID,
            benchmark_id,
            cancel=token,
            target_latency_seconds=LATENCY,
            target_cost_usd=COST,
        )

    assert instance.runs.list(COUNT_WORKFLOW_ID) == ()


def test_an_unknown_benchmark_or_workflow_is_not_found(
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)

    with pytest.raises(api.NotFoundError, match="is not configured"):
        instance.optimization.optimize(
            COUNT_WORKFLOW_ID, MISSING_ID, target_latency_seconds=LATENCY, target_cost_usd=COST
        )

    with pytest.raises(api.NotFoundError):
        instance.optimization.optimize(
            MISSING_ID, benchmark_id, target_latency_seconds=LATENCY, target_cost_usd=COST
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"generations": 0}, "at least one generation"),
        ({"target_latency_seconds": 0.0}, "greater than 0"),
        ({"target_cost_usd": -1.0}, "greater than 0"),
    ],
)
def test_a_session_that_could_not_run_is_refused_before_anything_runs(
    instance: api.Azathoth,
    change: dict[str, float],
    message: str,
) -> None:
    benchmark_id = counted(instance)
    arguments: dict[str, float] = {
        "target_latency_seconds": LATENCY,
        "target_cost_usd": COST,
        "generations": 1,
        **change,
    }

    with pytest.raises(api.InvalidArgumentError, match=message):
        instance.optimization.optimize(
            COUNT_WORKFLOW_ID,
            benchmark_id,
            target_latency_seconds=arguments["target_latency_seconds"],
            target_cost_usd=arguments["target_cost_usd"],
            generations=int(arguments["generations"]),
        )

    assert instance.runs.list(COUNT_WORKFLOW_ID) == ()


def test_an_empty_benchmark_is_refused(
    instance: api.Azathoth,
) -> None:
    benchmark_id = stocked_benchmark(instance)

    with pytest.raises(api.InvalidArgumentError, match="has no cases"):
        instance.optimization.optimize(
            COUNT_WORKFLOW_ID, benchmark_id, target_latency_seconds=LATENCY, target_cost_usd=COST
        )


def test_a_workflow_without_a_result_is_refused_as_missing_its_result(
    location: str,
    instance: api.Azathoth,
) -> None:
    benchmark_id = counted(instance)
    document = workflow(NO_RESULT_WORKFLOW_ID, tool_step(NO_RESULT_STEP_ID, "word_count"))
    del document["result"]
    open_repositories(location).workflows.save(decode_workflow_document(json.dumps(document)))

    with pytest.raises(
        api.WorkflowResultMissingError,
        match=f"Workflow {NO_RESULT_WORKFLOW_ID} does not declare a result.",
    ):
        instance.optimization.optimize(
            NO_RESULT_WORKFLOW_ID,
            benchmark_id,
            target_latency_seconds=LATENCY,
            target_cost_usd=COST,
        )

"""Contract tests for reading a benchmark's saved runs and comparisons (ADR 0130)."""

import shlex
from uuid import UUID

import pytest

from azathoth import api
from azathoth.cli.parsing import build_parser
from azathoth.evaluation import (
    BenchmarkDataset,
    EvaluationResult,
    EvaluationStatus,
)
from azathoth.persistence.repositories import open_repositories
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import WorkflowRunEvaluation
from tests.cli.test_benchmark_execution_rendering import (
    BENCHMARK_ID,
    EXACT_CASE_ID,
    EXECUTION_ID,
    FIRST_WORKFLOW_ID,
    RECORDED_AT,
    RUN_EXECUTION_ID,
    SECOND_WORKFLOW_ID,
    SEMANTIC_CASE_ID,
    create_comparison,
    create_run,
)

MISSING_ID = UUID("00000000-0000-4000-8000-0000000000ff")

EVALUATION_ID = UUID(int=102)


def parses(
    command: str,
) -> bool:
    """Return whether the CLI accepts one command an API value carries."""

    words = shlex.split(command)

    assert words[0] == "azathoth"

    build_parser().parse_args(words[1:])

    return True


@pytest.fixture
def stocked(
    location: str,
    instance: api.Azathoth,
) -> api.Azathoth:
    """Return the instance holding the benchmark, a saved run of it and a later comparison.

    The run names the benchmark's second revision by its content, and the
    run's first case keeps its evaluation.
    """

    repositories = open_repositories(location)
    benchmarks = repositories.benchmarks

    benchmarks.save(BenchmarkDataset(id=BENCHMARK_ID, name="classify", description="Classify."))
    second = benchmarks.save(
        BenchmarkDataset(id=BENCHMARK_ID, name="classify", description="Classify input.")
    )

    repositories.benchmark_executions.save(
        create_run().model_copy(
            update={
                "benchmark_digest": second.content_digest,
                "sensitivity": Sensitivity.RESTRICTED,
            }
        )
    )
    repositories.benchmark_executions.save(
        create_comparison().model_copy(
            update={"recorded_at": RECORDED_AT.replace(hour=13)},
        )
    )
    repositories.run_evaluations.save(
        WorkflowRunEvaluation(
            run_id=UUID(int=101),
            evaluation=EvaluationResult(
                id=EVALUATION_ID,
                evaluator_name="exact",
                score=1.0,
                status=EvaluationStatus.PASSED,
                reason="The result equals the expected value.",
            ),
        )
    )

    return instance


def test_a_benchmarks_executions_are_listed_newest_first(
    stocked: api.Azathoth,
) -> None:
    comparison, run = stocked.benchmarks.executions(BENCHMARK_ID)

    assert (comparison.execution_id, run.execution_id) == (EXECUTION_ID, RUN_EXECUTION_ID)
    assert comparison.kind == "compare"
    assert run.kind == "run"
    assert [
        summary.execution_id for summary in stocked.benchmarks.executions(BENCHMARK_ID, limit=1)
    ] == [EXECUTION_ID]
    assert all(parses(summary.command) for summary in (comparison, run))


def test_a_summary_says_what_ran_and_how_well(
    stocked: api.Azathoth,
) -> None:
    comparison, run = stocked.benchmarks.executions(BENCHMARK_ID)

    assert run.benchmark_revision == 2
    assert run.sensitivity == "restricted"
    assert run.case_count == 2
    (only,) = run.candidates
    assert (only.workflow_id, only.cases_passed, only.cases_run) == (FIRST_WORKFLOW_ID, 1, 2)
    assert only.accuracy == 0.5
    assert only.overall_score is None

    assert comparison.benchmark_revision is None
    assert comparison.sensitivity == "internal"
    assert [candidate.workflow_id for candidate in comparison.candidates] == [
        SECOND_WORKFLOW_ID,
        FIRST_WORKFLOW_ID,
    ]
    assert [candidate.overall_score for candidate in comparison.candidates] == [1.0, 0.5]


def test_a_run_is_read_with_every_case_and_its_evaluation(
    stocked: api.Azathoth,
) -> None:
    run = stocked.benchmarks.execution(RUN_EXECUTION_ID)

    assert run.kind == "run"
    assert run.scoring_policy is None
    (candidate,) = run.candidates
    assert candidate.workflow_name == "workflow 1"
    assert candidate.strategy_ids == (UUID(int=1),)
    assert candidate.scorecard is None
    assert candidate.judged_semantically is True
    assert (candidate.judge_calls, candidate.judge_cost_usd) == (1, 0.25)
    tallies = [
        (tally.comparison, tally.cases_passed, tally.cases_run) for tally in candidate.tallies
    ]
    assert tallies == [
        ("exact", 1, 1),
        ("semantic", 0, 1),
    ]

    exact, semantic = candidate.cases
    assert (exact.case_id, exact.passed, exact.run_id) == (EXACT_CASE_ID, True, UUID(int=101))
    assert (exact.score, exact.reason) == (1.0, "The result equals the expected value.")
    assert (semantic.case_id, semantic.passed) == (SEMANTIC_CASE_ID, False)
    assert (semantic.score, semantic.reason) == (None, None)
    assert parses(run.command)


def test_a_comparison_is_read_ranked_with_its_policy_and_scorecards(
    stocked: api.Azathoth,
) -> None:
    comparison = stocked.benchmarks.execution(EXECUTION_ID)

    assert comparison.scoring_policy == api.ScoringPolicySummary(
        target_latency_seconds=5.0,
        target_cost_usd=0.01,
    )
    winner, loser = comparison.candidates
    assert winner.workflow_id == SECOND_WORKFLOW_ID
    assert winner.scorecard is not None
    assert winner.scorecard.overall_score == 1.0
    assert loser.run_failures == 1
    assert loser.overall_score == 0.5


def test_executions_of_a_benchmark_since_removed_stay_readable(
    location: str,
    instance: api.Azathoth,
) -> None:
    open_repositories(location).benchmark_executions.save(create_run())

    (only,) = instance.benchmarks.executions(BENCHMARK_ID)

    assert only.execution_id == RUN_EXECUTION_ID
    assert only.benchmark_revision is None


def test_an_unknown_benchmark_or_execution_is_not_found(
    stocked: api.Azathoth,
) -> None:
    with pytest.raises(
        api.NotFoundError, match=f"Benchmark dataset {MISSING_ID} is not configured."
    ):
        stocked.benchmarks.executions(MISSING_ID)

    with pytest.raises(api.NotFoundError, match=f"Benchmark execution {MISSING_ID} was not found."):
        stocked.benchmarks.execution(MISSING_ID)

    with pytest.raises(api.InvalidArgumentError):
        stocked.benchmarks.executions(BENCHMARK_ID, limit=0)


def test_a_configured_benchmark_with_no_executions_lists_none(
    location: str,
    instance: api.Azathoth,
) -> None:
    open_repositories(location).benchmarks.save(
        BenchmarkDataset(id=BENCHMARK_ID, name="classify", description="Classify.")
    )

    assert instance.benchmarks.executions(BENCHMARK_ID) == ()

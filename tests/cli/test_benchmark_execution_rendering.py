"""Tests for rendering saved benchmark comparisons."""

from uuid import UUID

import pytest

from azathoth.cli import render_workflow_benchmark_comparison_execution
from azathoth.evaluation import OutcomeComparison
from azathoth.workflows import (
    WorkflowBenchmarkExecutionCandidate,
    WorkflowBenchmarkExecutionCase,
    WorkflowBenchmarkExecutionKind,
    WorkflowBenchmarkExecutionRecord,
    WorkflowCandidateSignature,
    WorkflowMetadata,
    WorkflowScorecard,
    WorkflowScoringPolicy,
)

EXECUTION_ID = UUID("e0e0e0e0-e0e0-40e0-80e0-e0e0e0e0e0e0")

BENCHMARK_ID = UUID("b0b0b0b0-b0b0-40b0-80b0-b0b0b0b0b0b0")

FIRST_WORKFLOW_ID = UUID("11111111-1111-4111-8111-111111111111")

SECOND_WORKFLOW_ID = UUID("22222222-2222-4222-8222-222222222222")

EXACT_CASE_ID = UUID("c1c1c1c1-c1c1-41c1-81c1-c1c1c1c1c1c1")

SEMANTIC_CASE_ID = UUID("c2c2c2c2-c2c2-42c2-82c2-c2c2c2c2c2c2")


def create_candidate(
    *,
    workflow_id: UUID,
    group: int,
    passed: tuple[bool, bool],
    run_failure: bool,
    semantic: bool,
    scorecard: WorkflowScorecard | None,
) -> WorkflowBenchmarkExecutionCandidate:
    """Create one compared candidate judged on an exact and a second case.

    The second case is semantic, judged by one call costing $0.25, when
    `semantic` is set, and exact otherwise.
    """

    return WorkflowBenchmarkExecutionCandidate(
        workflow=WorkflowMetadata(
            id=workflow_id,
            name=f"workflow {group}",
            description="Classify input.",
        ),
        candidate_signature=WorkflowCandidateSignature(
            workflow_id=workflow_id,
            strategy_ids=(UUID(int=group),),
        ),
        cases=(
            WorkflowBenchmarkExecutionCase(
                case_id=EXACT_CASE_ID,
                comparison=OutcomeComparison.EXACT,
                run_id=UUID(int=group * 100 + 1),
                evaluation_id=UUID(int=group * 100 + 2),
                passed=passed[0],
            ),
            WorkflowBenchmarkExecutionCase(
                case_id=SEMANTIC_CASE_ID,
                comparison=(OutcomeComparison.SEMANTIC if semantic else OutcomeComparison.EXACT),
                run_id=UUID(int=group * 100 + 3),
                evaluation_id=UUID(int=group * 100 + 4),
                passed=passed[1],
                run_failure=run_failure,
                judge_calls=1 if semantic and not run_failure else 0,
                judge_cost_usd=0.25 if semantic and not run_failure else 0.0,
            ),
        ),
        scorecard=scorecard,
    )


def create_scorecard(
    overall_score: float,
) -> WorkflowScorecard:
    """Create one distinguishable scorecard."""

    return WorkflowScorecard(
        quality_score=overall_score,
        reliability_score=1.0,
        latency_score=0.9,
        cost_score=0.8,
        overall_score=overall_score,
    )


def create_comparison(
    *,
    semantic: bool = True,
) -> WorkflowBenchmarkExecutionRecord:
    """Create one saved comparison whose second recorded candidate won."""

    loser = create_candidate(
        workflow_id=FIRST_WORKFLOW_ID,
        group=1,
        passed=(True, False),
        run_failure=True,
        semantic=semantic,
        scorecard=create_scorecard(0.5),
    )

    winner = create_candidate(
        workflow_id=SECOND_WORKFLOW_ID,
        group=2,
        passed=(True, True),
        run_failure=False,
        semantic=semantic,
        scorecard=create_scorecard(1.0),
    )

    return WorkflowBenchmarkExecutionRecord(
        id=EXECUTION_ID,
        benchmark_id=BENCHMARK_ID,
        kind=WorkflowBenchmarkExecutionKind.COMPARE,
        candidates=(
            loser,
            winner,
        ),
        ranking=(
            winner.id,
            loser.id,
        ),
        scoring_policy=WorkflowScoringPolicy(
            target_latency_seconds=5.0,
            target_cost_usd=0.01,
        ),
    )


def test_comparison_rendering_shows_every_candidate_in_rank_order() -> None:
    rendered = render_workflow_benchmark_comparison_execution(
        create_comparison(),
    )

    assert rendered == (
        f"Execution ID: {EXECUTION_ID}\n"
        f"Benchmark ID: {BENCHMARK_ID}\n"
        "\n"
        "Rank 1\n"
        f"Workflow ID: {SECOND_WORKFLOW_ID}\n"
        "Quality: 1.000000\n"
        "Reliability: 1.000000\n"
        "Latency: 0.900000\n"
        "Cost: 0.800000\n"
        "Overall: 1.000000\n"
        "Passed (exact): 1/1\n"
        "Passed (semantic): 1/1\n"
        "Run failures: 0\n"
        "Judge Calls: 1\n"
        "Judge Cost: $0.250000\n"
        "\n"
        "Rank 2\n"
        f"Workflow ID: {FIRST_WORKFLOW_ID}\n"
        "Quality: 0.500000\n"
        "Reliability: 1.000000\n"
        "Latency: 0.900000\n"
        "Cost: 0.800000\n"
        "Overall: 0.500000\n"
        "Passed (exact): 1/1\n"
        "Passed (semantic): 0/1\n"
        "Run failures: 1\n"
        "Judge Calls: 0\n"
        "Judge Cost: $0.000000"
    )


def test_comparison_rendering_omits_judging_without_semantic_cases() -> None:
    rendered = render_workflow_benchmark_comparison_execution(
        create_comparison(
            semantic=False,
        ),
    )

    assert "Passed (exact): 2/2\nRun failures: 0\n" in rendered
    assert rendered.endswith("Passed (exact): 1/2\nRun failures: 1")
    assert "Judge" not in rendered
    assert "semantic" not in rendered


def test_comparison_rendering_rejects_a_benchmark_run() -> None:
    run = WorkflowBenchmarkExecutionRecord(
        id=EXECUTION_ID,
        benchmark_id=BENCHMARK_ID,
        kind=WorkflowBenchmarkExecutionKind.RUN,
        candidates=(
            create_candidate(
                workflow_id=FIRST_WORKFLOW_ID,
                group=1,
                passed=(True, True),
                run_failure=False,
                semantic=False,
                scorecard=None,
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match=f"^Benchmark execution {EXECUTION_ID} is not a comparison.$",
    ):
        render_workflow_benchmark_comparison_execution(run)

"""Tests for benchmark workflow ranking rendering."""

from uuid import UUID

from azathoth.cli import (
    render_workflow_benchmark_ranking,
)
from azathoth.workflows import (
    WorkflowBenchmarkRankedCandidate,
    WorkflowBenchmarkRanking,
    WorkflowScorecard,
)

FIRST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

BENCHMARK_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_ranking() -> WorkflowBenchmarkRanking:
    """Create deterministic benchmark ranking evidence."""

    return WorkflowBenchmarkRanking(
        entries=(
            WorkflowBenchmarkRankedCandidate(
                rank=1,
                name=str(FIRST_WORKFLOW_ID),
                scorecard=WorkflowScorecard(
                    quality_score=1.0,
                    reliability_score=0.95,
                    latency_score=0.90,
                    cost_score=0.85,
                    overall_score=0.925,
                    rationale="First workflow aggregate.",
                ),
            ),
            WorkflowBenchmarkRankedCandidate(
                rank=2,
                name=str(SECOND_WORKFLOW_ID),
                scorecard=WorkflowScorecard(
                    quality_score=0.75,
                    reliability_score=0.90,
                    latency_score=0.80,
                    cost_score=0.70,
                    overall_score=0.7875,
                    rationale="Second workflow aggregate.",
                ),
            ),
        )
    )


def test_benchmark_ranking_rendering_identifies_dataset() -> None:
    rendered = render_workflow_benchmark_ranking(
        create_ranking(),
        benchmark_id=BENCHMARK_ID,
    )

    assert f"Benchmark ID: {BENCHMARK_ID}\n" in rendered


def test_benchmark_ranking_rendering_identifies_every_workflow() -> None:
    rendered = render_workflow_benchmark_ranking(
        create_ranking(),
        benchmark_id=BENCHMARK_ID,
    )

    assert f"Workflow ID: {FIRST_WORKFLOW_ID}\n" in rendered

    assert f"Workflow ID: {SECOND_WORKFLOW_ID}\n" in rendered


def test_benchmark_ranking_rendering_includes_ranks() -> None:
    rendered = render_workflow_benchmark_ranking(
        create_ranking(),
        benchmark_id=BENCHMARK_ID,
    )

    assert "Rank 1\n" in rendered
    assert "Rank 2\n" in rendered


def test_benchmark_ranking_rendering_includes_all_score_dimensions() -> None:
    rendered = render_workflow_benchmark_ranking(
        create_ranking(),
        benchmark_id=BENCHMARK_ID,
    )

    assert "Quality: 1.000000\n" in rendered
    assert "Reliability: 0.950000\n" in rendered
    assert "Latency: 0.900000\n" in rendered
    assert "Cost: 0.850000\n" in rendered
    assert "Overall: 0.925000\n" in rendered

    assert "Quality: 0.750000\n" in rendered
    assert "Overall: 0.787500" in rendered

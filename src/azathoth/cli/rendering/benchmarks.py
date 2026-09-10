"""Human-readable workflow benchmark rendering."""

from uuid import UUID

from azathoth.workflows import (
    WorkflowBenchmarkRanking,
    WorkflowBenchmarkResult,
)


def render_workflow_benchmark_result(
    result: WorkflowBenchmarkResult,
    *,
    workflow_id: UUID,
) -> str:
    """Render aggregate workflow benchmark evidence."""

    return "\n".join(
        (
            f"Benchmark ID: {result.dataset_id}",
            f"Workflow ID: {workflow_id}",
            f"Cases Run: {result.cases_run}",
            f"Cases Passed: {result.cases_passed}",
            f"Accuracy: {result.accuracy:.6f}",
            f"Total Tokens: {result.total_tokens}",
            f"Total Latency: {result.total_latency_ms} ms",
            f"Total Cost: ${result.total_cost_usd:.6f}",
        )
    )


def render_workflow_benchmark_ranking(
    ranking: WorkflowBenchmarkRanking,
    *,
    benchmark_id: UUID,
) -> str:
    """Render ranked configured workflow benchmark evidence."""

    lines = [
        f"Benchmark ID: {benchmark_id}",
    ]

    for entry in ranking.entries:
        scorecard = entry.scorecard

        lines.extend(
            (
                "",
                f"Rank {entry.rank}",
                f"Workflow ID: {entry.name}",
                f"Quality: {scorecard.quality_score:.6f}",
                f"Reliability: {scorecard.reliability_score:.6f}",
                f"Latency: {scorecard.latency_score:.6f}",
                f"Cost: {scorecard.cost_score:.6f}",
                f"Overall: {scorecard.overall_score:.6f}",
            )
        )

    return "\n".join(
        lines,
    )

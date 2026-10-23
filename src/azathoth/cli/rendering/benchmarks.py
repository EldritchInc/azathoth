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
    execution_id: UUID | None = None,
) -> str:
    """Render aggregate workflow benchmark evidence.

    A recorded result leads with the identifier of its saved execution, so
    the operator can inspect it again later.

    Pass counts are broken down by comparison after overall accuracy, so
    benchmarks mixing comparisons show which kind of case is failing. The
    run-failure count follows, so failed runs are told apart from wrong
    answers. When any case was judged semantically, judge calls and judge
    cost follow the workflow totals, kept apart because judging is
    Azathoth's own cost rather than the workflow's.
    """

    lines = [
        *((f"Execution ID: {execution_id}",) if execution_id is not None else ()),
        f"Benchmark ID: {result.dataset_id}",
        f"Workflow ID: {workflow_id}",
        f"Cases Run: {result.cases_run}",
        f"Cases Passed: {result.cases_passed}",
        f"Accuracy: {result.accuracy:.6f}",
        *(
            f"Passed ({tally.comparison.value}): {tally.cases_passed}/{tally.cases_run}"
            for tally in result.comparison_tallies
        ),
        f"Run failures: {result.run_failures}",
        f"Total Tokens: {result.total_tokens}",
        f"Total Latency: {result.total_latency_ms} ms",
        f"Total Cost: ${result.total_cost_usd:.6f}",
    ]

    if result.judged_semantically:
        lines.extend(
            (
                f"Judge Calls: {result.judge_calls}",
                f"Judge Cost: ${result.judge_cost_usd:.6f}",
            )
        )

    return "\n".join(lines)


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

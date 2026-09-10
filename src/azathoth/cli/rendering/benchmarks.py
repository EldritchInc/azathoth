"""Human-readable workflow benchmark rendering."""

from uuid import UUID

from azathoth.workflows import WorkflowBenchmarkResult


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

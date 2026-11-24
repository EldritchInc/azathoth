"""Human-readable workflow benchmark rendering.

`benchmark run` here renders the result it measured; given `--remote`, it
renders the execution the remote saved, as the service API returns it, in
the same lines (ADR 0140).
"""

from uuid import UUID

from azathoth import api
from azathoth.workflows import (
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


def render_benchmark_run(
    execution: api.BenchmarkExecutionDetail,
) -> str:
    """Render a saved benchmark run as `render_workflow_benchmark_result` renders its result.

    Totals the API could not measure, because a case run is no longer
    kept, are shown as unknown.

    Raises:
        ValueError: The execution is not a run.
    """

    if execution.kind != "run":
        raise ValueError(f"Benchmark execution {execution.execution_id} is not a run.")

    (candidate,) = execution.candidates

    lines = [
        f"Execution ID: {execution.execution_id}",
        f"Benchmark ID: {execution.benchmark_id}",
        f"Workflow ID: {candidate.workflow_id}",
        f"Cases Run: {candidate.cases_run}",
        f"Cases Passed: {candidate.cases_passed}",
        f"Accuracy: {candidate.accuracy:.6f}",
        *(
            f"Passed ({tally.comparison}): {tally.cases_passed}/{tally.cases_run}"
            for tally in candidate.tallies
        ),
        f"Run failures: {candidate.run_failures}",
        "Total Tokens: "
        + (str(candidate.total_tokens) if candidate.total_tokens is not None else "unknown"),
        "Total Latency: "
        + (
            f"{candidate.total_latency_ms} ms"
            if candidate.total_latency_ms is not None
            else "unknown"
        ),
        "Total Cost: "
        + (
            f"${candidate.total_cost_usd:.6f}"
            if candidate.total_cost_usd is not None
            else "unknown"
        ),
    ]

    if candidate.judged_semantically:
        lines.extend(
            (
                f"Judge Calls: {candidate.judge_calls}",
                f"Judge Cost: ${candidate.judge_cost_usd:.6f}",
            )
        )

    return "\n".join(lines)

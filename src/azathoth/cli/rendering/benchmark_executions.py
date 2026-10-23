"""Human-readable rendering of saved workflow benchmark executions."""

from azathoth.workflows import (
    WorkflowBenchmarkExecutionCandidate,
    WorkflowBenchmarkExecutionKind,
    WorkflowBenchmarkExecutionRecord,
    WorkflowScorecard,
)


def render_workflow_benchmark_comparison_execution(
    execution: WorkflowBenchmarkExecutionRecord,
) -> str:
    """Render one recorded benchmark comparison, best candidate first.

    Each ranked candidate shows its scorecard, then its pass counts per
    comparison and its run failures, so a ranking can be explained by which
    kind of case each workflow got wrong. When a candidate had semantically
    judged cases, its judge calls and judge cost follow, kept apart from the
    scorecard because judging is Azathoth's own cost.

    Raises:
        ValueError: The execution is not a comparison.
    """

    if execution.kind is not WorkflowBenchmarkExecutionKind.COMPARE:
        raise ValueError(f"Benchmark execution {execution.id} is not a comparison.")

    lines = [
        f"Execution ID: {execution.id}",
        f"Benchmark ID: {execution.benchmark_id}",
    ]

    for rank, candidate in enumerate(execution.ranked_candidates, start=1):
        scorecard = _scorecard(
            execution,
            candidate,
        )

        lines.extend(
            (
                "",
                f"Rank {rank}",
                f"Workflow ID: {candidate.workflow.id}",
                f"Quality: {scorecard.quality_score:.6f}",
                f"Reliability: {scorecard.reliability_score:.6f}",
                f"Latency: {scorecard.latency_score:.6f}",
                f"Cost: {scorecard.cost_score:.6f}",
                f"Overall: {scorecard.overall_score:.6f}",
                *render_candidate_evidence(candidate),
            )
        )

    return "\n".join(lines)


def render_candidate_evidence(
    candidate: WorkflowBenchmarkExecutionCandidate,
) -> tuple[str, ...]:
    """Render one candidate's pass counts, run failures, and judge totals."""

    return (
        *(
            f"Passed ({tally.comparison.value}): {tally.cases_passed}/{tally.cases_run}"
            for tally in candidate.comparison_tallies
        ),
        f"Run failures: {candidate.run_failures}",
        *(
            (
                f"Judge Calls: {candidate.judge_calls}",
                f"Judge Cost: ${candidate.judge_cost_usd:.6f}",
            )
            if candidate.judged_semantically
            else ()
        ),
    )


def _scorecard(
    execution: WorkflowBenchmarkExecutionRecord,
    candidate: WorkflowBenchmarkExecutionCandidate,
) -> WorkflowScorecard:
    """Return a compared candidate's scorecard.

    Raises:
        ValueError: The candidate was recorded without a scorecard.
    """

    if candidate.scorecard is None:
        raise ValueError(
            f"Benchmark execution {execution.id} candidate {candidate.id} has no scorecard."
        )

    return candidate.scorecard

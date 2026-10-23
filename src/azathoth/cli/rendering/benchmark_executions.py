"""Human-readable rendering of saved workflow benchmark executions."""

from collections.abc import Iterable

from azathoth.workflows import (
    WorkflowBenchmarkExecutionCandidate,
    WorkflowBenchmarkExecutionCase,
    WorkflowBenchmarkExecutionKind,
    WorkflowBenchmarkExecutionRecord,
    WorkflowScorecard,
)


def render_workflow_benchmark_execution_summaries(
    executions: Iterable[WorkflowBenchmarkExecutionRecord],
) -> str:
    """Render one line per saved execution in the order given.

    Each line contains the execution ID, recorded time, kind, candidate
    count, and case count. A run then names its workflow and accuracy; a
    comparison names its winning workflow and the winner's overall score.
    """

    return "\n".join(_render_summary(execution) for execution in executions)


def render_workflow_benchmark_execution(
    execution: WorkflowBenchmarkExecutionRecord,
) -> str:
    """Render one saved execution with every candidate and every case.

    A comparison lists its scoring targets and winner, then its candidates in
    rank order with their scorecards. A run lists its one candidate. Every
    candidate shows its pass counts, run failures, and judge totals when it
    had semantic cases, then one line per case naming the case, its outcome,
    its comparison, and the run and evaluation that judged it.
    """

    lines = [
        f"Execution ID: {execution.id}",
        f"Recorded: {execution.recorded_at.isoformat()}",
        f"Kind: {execution.kind.value}",
        f"Benchmark ID: {execution.benchmark_id}",
        f"Candidates: {len(execution.candidates)}",
        f"Cases: {len(execution.case_ids)}",
    ]

    policy = execution.scoring_policy

    if policy is not None:
        lines.extend(
            (
                f"Target Latency: {policy.target_latency_seconds:.6f} s",
                f"Target Cost: ${policy.target_cost_usd:.6f}",
            )
        )

    winner = execution.winner

    if winner is not None:
        lines.append(f"Winner Workflow ID: {winner.workflow.id}")

    ranked = execution.kind is WorkflowBenchmarkExecutionKind.COMPARE

    for rank, candidate in enumerate(execution.ranked_candidates, start=1):
        lines.extend(
            (
                "",
                f"Rank {rank}" if ranked else "Candidate",
                f"Candidate ID: {candidate.id}",
                f"Workflow: {candidate.workflow.name}",
                f"Workflow ID: {candidate.workflow.id}",
                "Strategy IDs: "
                + ", ".join(
                    str(strategy_id) for strategy_id in candidate.candidate_signature.strategy_ids
                ),
                f"Passed: {candidate.cases_passed}/{candidate.cases_run}",
                f"Accuracy: {candidate.accuracy:.6f}",
                *render_candidate_evidence(candidate),
                *(
                    _render_scorecard(
                        _scorecard(
                            execution,
                            candidate,
                        )
                    )
                    if ranked
                    else ()
                ),
                *(_render_case(case) for case in candidate.cases),
            )
        )

    return "\n".join(lines)


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


def _render_summary(
    execution: WorkflowBenchmarkExecutionRecord,
) -> str:
    """Render one saved execution summary line."""

    count = len(execution.candidates)

    prefix = (
        f"{execution.id}  {execution.recorded_at.isoformat()}  {execution.kind.value}  "
        f"{count} {'candidate' if count == 1 else 'candidates'}  "
        f"{len(execution.case_ids)} cases"
    )

    winner = execution.winner

    if winner is None:
        (candidate,) = execution.candidates

        return f"{prefix}  workflow {candidate.workflow.id}  accuracy {candidate.accuracy:.6f}"

    return (
        f"{prefix}  winner {winner.workflow.id}  "
        f"overall {_scorecard(execution, winner).overall_score:.6f}"
    )


def _render_scorecard(
    scorecard: WorkflowScorecard,
) -> tuple[str, ...]:
    """Render one candidate's scorecard dimensions and rationale."""

    return (
        f"Quality: {scorecard.quality_score:.6f}",
        f"Reliability: {scorecard.reliability_score:.6f}",
        f"Latency: {scorecard.latency_score:.6f}",
        f"Cost: {scorecard.cost_score:.6f}",
        f"Overall: {scorecard.overall_score:.6f}",
        *((f"Rationale: {scorecard.rationale}",) if scorecard.rationale else ()),
    )


def _render_case(
    case: WorkflowBenchmarkExecutionCase,
) -> str:
    """Render one case outcome with the evidence that judged it."""

    outcome = "passed" if case.passed else "failed"

    return (
        f"Case {case.case_id}: {outcome}  {case.comparison.value}  "
        f"run {case.run_id}  evaluation {case.evaluation_id}"
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

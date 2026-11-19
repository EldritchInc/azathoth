"""Human-readable rendering of saved workflow benchmark executions.

Each renderer reads the service API's view of an execution (ADR 0130). A
saved record is read as the API reads it, so either renders the same.
"""

from collections.abc import Iterable

from azathoth import api
from azathoth.api.benchmark_executions import execution_detail, execution_summary
from azathoth.cli.rendering.sensitivity import render_sensitivity_lines
from azathoth.workflows import WorkflowBenchmarkExecutionRecord

Execution = api.BenchmarkExecutionDetail | WorkflowBenchmarkExecutionRecord
"""An execution as the API returns it, or as it was saved."""

ExecutionSummary = api.BenchmarkExecutionSummary | WorkflowBenchmarkExecutionRecord
"""An execution as a list of them returns it, or as it was saved."""


def _detail(
    execution: Execution,
) -> api.BenchmarkExecutionDetail:
    """Return the API's view of an execution."""

    if isinstance(execution, WorkflowBenchmarkExecutionRecord):
        return execution_detail(execution)

    return execution


def render_workflow_benchmark_execution_summaries(
    executions: Iterable[ExecutionSummary],
) -> str:
    """Render one line per saved execution in the order given.

    Each line contains the execution ID, recorded time, kind, candidate
    count, and case count. A run then names its workflow and accuracy; a
    comparison names its winning workflow and the winner's overall score.
    """

    return "\n".join(
        _render_summary(
            execution_summary(execution)
            if isinstance(execution, WorkflowBenchmarkExecutionRecord)
            else execution
        )
        for execution in executions
    )


def render_workflow_benchmark_execution(
    execution: Execution,
) -> str:
    """Render one saved execution with every candidate and every case.

    A comparison lists its scoring targets and winner, then its candidates in
    rank order with their scorecards. A run lists its one candidate. Every
    candidate shows its pass counts, run failures, and judge totals when it
    had semantic cases, then one line per case naming the case, its outcome,
    its comparison, and the run and evaluation that judged it.
    """

    detail = _detail(execution)
    ranked = detail.kind == "compare"
    lines = [
        f"Execution ID: {detail.execution_id}",
        f"Recorded: {detail.recorded_at.isoformat()}",
        f"Kind: {detail.kind}",
        f"Benchmark ID: {detail.benchmark_id}",
        f"Benchmark Digest: {_render_digest(detail.benchmark_digest)}",
        *render_sensitivity_lines(detail.sensitivity),
        f"Candidates: {len(detail.candidates)}",
        f"Cases: {detail.case_count}",
    ]

    policy = detail.scoring_policy

    if policy is not None:
        lines.extend(
            (
                f"Target Latency: {policy.target_latency_seconds:.6f} s",
                f"Target Cost: ${policy.target_cost_usd:.6f}",
            )
        )

    if ranked:
        lines.append(f"Winner Workflow ID: {detail.candidates[0].workflow_id}")

    for rank, candidate in enumerate(detail.candidates, start=1):
        lines.extend(
            (
                "",
                f"Rank {rank}" if ranked else "Candidate",
                f"Candidate ID: {candidate.candidate_id}",
                f"Workflow: {candidate.workflow_name}",
                f"Workflow ID: {candidate.workflow_id}",
                "Workflow Revision: "
                + (
                    str(candidate.workflow_revision)
                    if candidate.workflow_revision is not None
                    else "unknown"
                ),
                "Strategy IDs: "
                + ", ".join(str(strategy_id) for strategy_id in candidate.strategy_ids),
                f"Passed: {candidate.cases_passed}/{candidate.cases_run}",
                f"Accuracy: {candidate.accuracy:.6f}",
                *render_candidate_evidence(candidate),
                *(_render_scorecard(_scorecard(detail, candidate)) if ranked else ()),
                *(_render_case(case) for case in candidate.cases),
            )
        )

    return "\n".join(lines)


def render_workflow_benchmark_comparison_execution(
    execution: Execution,
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

    detail = _detail(execution)

    if detail.kind != "compare":
        raise ValueError(f"Benchmark execution {detail.execution_id} is not a comparison.")

    lines = [
        f"Execution ID: {detail.execution_id}",
        f"Benchmark ID: {detail.benchmark_id}",
        *render_sensitivity_lines(detail.sensitivity),
    ]

    for rank, candidate in enumerate(detail.candidates, start=1):
        scorecard = _scorecard(detail, candidate)

        lines.extend(
            (
                "",
                f"Rank {rank}",
                f"Workflow ID: {candidate.workflow_id}",
                f"Quality: {scorecard.quality_score:.6f}",
                f"Reliability: {scorecard.reliability_score:.6f}",
                f"Latency: {scorecard.latency_score:.6f}",
                f"Cost: {scorecard.cost_score:.6f}",
                *(
                    (f"Citations: {scorecard.citation_score:.6f}",)
                    if scorecard.citation_score is not None
                    else ()
                ),
                f"Overall: {scorecard.overall_score:.6f}",
                *render_candidate_evidence(candidate),
            )
        )

    return "\n".join(lines)


def render_candidate_evidence(
    candidate: api.ExecutionCandidate,
) -> tuple[str, ...]:
    """Render one candidate's pass counts, run failures, and judge totals."""

    return (
        *(
            f"Passed ({tally.comparison}): {tally.cases_passed}/{tally.cases_run}"
            for tally in candidate.tallies
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
    execution: api.BenchmarkExecutionSummary,
) -> str:
    """Render one saved execution summary line."""

    count = len(execution.candidates)

    prefix = (
        f"{execution.execution_id}  {execution.recorded_at.isoformat()}  {execution.kind}  "
        f"{count} {'candidate' if count == 1 else 'candidates'}  "
        f"{execution.case_count} cases"
    )

    best = execution.candidates[0]

    if execution.kind != "compare":
        return f"{prefix}  workflow {best.workflow_id}  accuracy {best.accuracy:.6f}"

    if best.overall_score is None:
        raise ValueError(
            f"Benchmark execution {execution.execution_id} candidate {best.candidate_id} "
            "has no scorecard."
        )

    return f"{prefix}  winner {best.workflow_id}  overall {best.overall_score:.6f}"


def _render_scorecard(
    scorecard: api.CandidateScorecard,
) -> tuple[str, ...]:
    """Render one candidate's scorecard dimensions and rationale."""

    return (
        f"Quality: {scorecard.quality_score:.6f}",
        f"Reliability: {scorecard.reliability_score:.6f}",
        f"Latency: {scorecard.latency_score:.6f}",
        f"Cost: {scorecard.cost_score:.6f}",
        *(
            (f"Citations: {scorecard.citation_score:.6f}",)
            if scorecard.citation_score is not None
            else ()
        ),
        f"Overall: {scorecard.overall_score:.6f}",
        *((f"Rationale: {scorecard.rationale}",) if scorecard.rationale else ()),
    )


def _render_case(
    case: api.ExecutionCaseResult,
) -> str:
    """Render one case outcome with the evidence that judged it."""

    outcome = "passed" if case.passed else "failed"

    return (
        f"Case {case.case_id}: {outcome}  {case.comparison}  "
        f"run {case.run_id}  evaluation {case.evaluation_id}"
    )


def _scorecard(
    execution: api.BenchmarkExecutionDetail,
    candidate: api.ExecutionCandidate,
) -> api.CandidateScorecard:
    """Return a compared candidate's scorecard.

    Raises:
        ValueError: The candidate was recorded without a scorecard.
    """

    if candidate.scorecard is None:
        raise ValueError(
            f"Benchmark execution {execution.execution_id} candidate {candidate.candidate_id} "
            "has no scorecard."
        )

    return candidate.scorecard


def _render_digest(
    digest: str | None,
) -> str:
    """Render the short form `benchmark history` lists, or that it is unknown."""

    return digest[:12] if digest is not None else "unknown"

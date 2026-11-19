"""Human-readable workflow experiment rendering.

Each renderer takes the service API's view of an experiment (ADR 0131), or
a recorded experiment, which it reads as the API would, so the command line
prints what the API returns.
"""

from collections.abc import Iterable
from uuid import UUID

from azathoth.api import (
    ExperimentCandidate,
    ExperimentCase,
    ExperimentDetail,
    ExperimentSummary,
)
from azathoth.api.experiments import experiment_detail, experiment_summary
from azathoth.cli.rendering.sensitivity import render_sensitivity_lines
from azathoth.workflows import WorkflowExperimentRecord


def render_workflow_experiment_summaries(
    experiments: Iterable[ExperimentSummary | WorkflowExperimentRecord],
) -> str:
    """Render one line per experiment in the order given.

    Each line contains the experiment ID, recorded time, candidate count,
    case count, winning observation ID, and winning overall score.
    """

    return "\n".join(
        _render_summary(
            experiment_summary(experiment)
            if isinstance(experiment, WorkflowExperimentRecord)
            else experiment
        )
        for experiment in experiments
    )


def render_workflow_experiment(
    experiment: ExperimentDetail | WorkflowExperimentRecord,
) -> str:
    """Render one durable experiment with every observation in rank order.

    Each observation lists its pass count and one line per case naming the
    case, its outcome, and the run and evaluation that judged it. Records
    written before benchmark-driven optimization have no benchmark, no case
    identifiers, and unknown outcomes, each rendered as such.

    An observation whose evaluation called judges ends with its judge calls
    and their cost, which are never part of its scores. Observations judged
    without judges, and records written before judge evidence was recorded,
    show no judge lines.
    """

    detail = (
        experiment_detail(experiment)
        if isinstance(experiment, WorkflowExperimentRecord)
        else experiment
    )

    benchmark = str(detail.benchmark_id) if detail.benchmark_id is not None else "none"

    lines = [
        f"Experiment ID: {detail.experiment_id}",
        f"Recorded: {detail.recorded_at.isoformat()}",
        f"Benchmark: {benchmark}",
        "Benchmark Digest: "
        + (detail.benchmark_digest[:12] if detail.benchmark_digest is not None else "unknown"),
        *render_sensitivity_lines(detail.sensitivity),
        f"Candidates: {detail.candidate_count}",
        f"Cases: {detail.case_count}",
        f"Winner Observation ID: {detail.winner_observation_id}",
    ]

    for candidate in detail.candidates:
        _append_observation(
            lines,
            detail.workflow_name,
            detail.workflow_id,
            candidate,
        )

    return "\n".join(lines)


def _render_summary(
    experiment: ExperimentSummary,
) -> str:
    """Render one experiment summary line."""

    return (
        f"{experiment.experiment_id}  {experiment.recorded_at.isoformat()}  "
        f"{experiment.candidate_count} candidates  "
        f"{experiment.case_count} cases  "
        f"winner {experiment.winner_observation_id}  overall {experiment.winner_score:.6f}"
    )


def _append_observation(
    lines: list[str],
    workflow_name: str,
    workflow_id: UUID,
    candidate: ExperimentCandidate,
) -> None:
    """Append one ranked experiment observation."""

    scorecard = candidate.scorecard

    cases_passed = candidate.cases_passed

    lines.extend(
        (
            "",
            f"Rank {candidate.rank}",
            f"Observation ID: {candidate.observation_id}",
            f"Workflow: {workflow_name}",
            f"Workflow ID: {workflow_id}",
            "Workflow Revision: "
            + (
                str(candidate.workflow_revision)
                if candidate.workflow_revision is not None
                else "unknown"
            ),
            "Strategy IDs: "
            + ", ".join(str(strategy_id) for strategy_id in candidate.strategy_ids),
            (
                f"Passed: {cases_passed}/{candidate.cases_run}"
                if cases_passed is not None
                else "Passed: unknown"
            ),
            *(_render_case(case) for case in candidate.cases),
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
        )
    )

    if scorecard.rationale:
        lines.append(f"Rationale: {scorecard.rationale}")

    if candidate.judge_calls:
        lines.extend(
            (
                f"Judge Calls: {candidate.judge_calls}",
                f"Judge Cost: ${candidate.judge_cost_usd:.6f}",
            )
        )


def _render_case(
    case: ExperimentCase,
) -> str:
    """Render one case outcome with the evidence that judged it."""

    case_label = str(case.case_id) if case.case_id is not None else "none"

    if case.passed is None:
        outcome = "unknown"
    elif case.passed:
        outcome = "passed"
    else:
        outcome = "failed"

    return f"Case {case_label}: {outcome}  run {case.run_id}  evaluation {case.evaluation_id}"

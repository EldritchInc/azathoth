"""Human-readable workflow experiment rendering.

Each renderer takes the service API's view of an experiment (ADR 0131), or
a recorded experiment, which it reads as the API would, so the command line
prints what the API returns.
"""

from collections.abc import Iterable
from uuid import UUID

from azathoth.api import (
    ComparedCase,
    ExperimentCandidate,
    ExperimentCase,
    ExperimentComparison,
    ExperimentDetail,
    ExperimentSummary,
    RunCosts,
    Savings,
    SavingsProjection,
)
from azathoth.api.experiments import PROJECTION_DAYS, experiment_detail, experiment_summary
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


def _outcome(
    passed: bool | None,
) -> str:
    """Return how a case went, as a word."""

    if passed is None:
        return "unknown"

    return "passed" if passed else "failed"


def _compared_case(
    case: ComparedCase,
) -> str:
    """Render one case as the winner and the baseline did on it."""

    label = str(case.case_id) if case.case_id is not None else "none"

    return (
        f"Case {label}: winner {_outcome(case.winner_passed)}, "
        f"baseline {_outcome(case.baseline_passed)}"
    )


def _run_line(
    side: str,
    costs: RunCosts,
) -> str:
    """Render what one side's runs cost and took, on the mean."""

    if costs.runs == 0:
        return f"{side} Run: unknown, no case run is kept"

    cost = f"${costs.cost_usd:.6f}" if costs.cost_usd is not None else "cost unknown"
    latency = (
        f"{costs.latency_seconds:.2f} s" if costs.latency_seconds is not None else "time unknown"
    )
    plural = "run" if costs.runs == 1 else "runs"

    return f"{side} Run: {cost}, {latency}, over {costs.runs} {plural}"


def _percent(
    value: float | None,
) -> str:
    """Render a share of the baseline, as a magnitude, or nothing when it is undefined."""

    return "" if value is None else f" ({abs(value):.1f}%)"


def _money(
    saved: float | None,
    percent: float | None,
) -> str:
    """Render a saving in dollars, said as a cost when it is negative."""

    if saved is None:
        return "cost unknown"

    if saved < 0:
        return f"costs ${-saved:.6f} more{_percent(percent)}"

    return f"${saved:.6f}{_percent(percent)}"


def _time(
    saved: float | None,
    percent: float | None,
) -> str:
    """Render a saving in seconds, said as a delay when it is negative."""

    if saved is None:
        return "time unknown"

    if saved < 0:
        return f"takes {-saved:.2f} s longer{_percent(percent)}"

    return f"{saved:.2f} s{_percent(percent)}"


def _savings_line(
    savings: Savings,
) -> str:
    """Render what the winner saves per run on the benchmark."""

    return (
        f"Saves Per Run: {_money(savings.cost_usd, savings.cost_percent)}, "
        f"{_time(savings.latency_seconds, savings.latency_percent)}"
    )


def _projection_line(
    projection: SavingsProjection | None,
    window_days: int,
) -> str:
    """Render the saving projected over production's recent invocations, labelled as one."""

    if projection is None:
        return f"Projection: none; production made no invocation in the last {window_days} days"

    plural = "invocation" if projection.invocations == 1 else "invocations"

    return (
        f"Projection: over {projection.invocations} production {plural} in the last "
        f"{projection.window_days} days, {_money(projection.cost_usd, None)} and "
        f"{_time(projection.latency_seconds, None)}; a projection, not a measurement"
    )


def render_experiment_comparison(
    comparison: ExperimentComparison,
) -> str:
    """Render one experiment's winner beside its baseline, and what promoting it would save.

    Each step the two ran on different models is named with both, baseline
    first. The saving is measured per run on the benchmark; the projection
    over production's recent invocations is said to be one.
    """

    lines = [
        f"Experiment ID: {comparison.experiment_id}",
        f"Workflow ID: {comparison.workflow_id}",
    ]

    if comparison.baseline is None or comparison.baseline_candidate is None:
        lines.extend(
            (
                f"Compared With: nothing. {comparison.reason}",
                f"Winner Observation ID: {comparison.winner.observation_id}",
                _run_line("Winner", comparison.winner_runs),
            )
        )

        return "\n".join(lines)

    lines.extend(
        (
            f"Compared With: {comparison.baseline}",
            f"Winner Observation ID: {comparison.winner.observation_id}",
            f"Baseline Observation ID: {comparison.baseline_candidate.observation_id}",
        )
    )

    lines.extend(
        f"Step {step.step_id}: {step.baseline_model or 'no model'} -> "
        f"{step.winner_model or 'no model'}"
        for step in comparison.steps
        if step.differs
    )

    lines.extend(_compared_case(case) for case in comparison.cases)

    lines.append(_run_line("Winner", comparison.winner_runs))

    if comparison.baseline_runs is not None:
        lines.append(_run_line("Baseline", comparison.baseline_runs))

    if comparison.savings is not None:
        lines.extend(
            (
                _savings_line(comparison.savings),
                _projection_line(comparison.projection, PROJECTION_DAYS),
            )
        )

    lines.append(f"Promote: {comparison.command}")

    return "\n".join(lines)

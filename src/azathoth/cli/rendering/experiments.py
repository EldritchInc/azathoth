"""Human-readable workflow experiment rendering."""

from collections.abc import Iterable

from azathoth.workflows import (
    WorkflowExperimentCaseObservation,
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
)


def render_workflow_experiment_summaries(
    experiments: Iterable[WorkflowExperimentRecord],
) -> str:
    """Render one line per experiment in the order given.

    Each line contains the experiment ID, recorded time, candidate count,
    case count, winning observation ID, and winning overall score.
    """

    return "\n".join(_render_summary(experiment) for experiment in experiments)


def render_workflow_experiment(
    experiment: WorkflowExperimentRecord,
) -> str:
    """Render one durable experiment with every observation in rank order.

    Each observation lists its pass count and one line per case naming the
    case, its outcome, and the run and evaluation that judged it. Records
    written before benchmark-driven optimization have no benchmark, no case
    identifiers, and unknown outcomes, each rendered as such.
    """

    benchmark = str(experiment.benchmark_id) if experiment.benchmark_id is not None else "none"

    lines = [
        f"Experiment ID: {experiment.id}",
        f"Recorded: {experiment.recorded_at.isoformat()}",
        f"Benchmark: {benchmark}",
        f"Candidates: {len(experiment.observations)}",
        f"Cases: {_case_count(experiment)}",
        f"Winner Observation ID: {experiment.winner.id}",
    ]

    for rank, observation in enumerate(
        experiment.ranked_observations,
        start=1,
    ):
        _append_observation(
            lines,
            rank,
            observation,
        )

    return "\n".join(lines)


def _render_summary(
    experiment: WorkflowExperimentRecord,
) -> str:
    """Render one experiment summary line."""

    winner = experiment.winner

    return (
        f"{experiment.id}  {experiment.recorded_at.isoformat()}  "
        f"{len(experiment.observations)} candidates  "
        f"{_case_count(experiment)} cases  "
        f"winner {winner.id}  overall {winner.scorecard.overall_score:.6f}"
    )


def _case_count(
    experiment: WorkflowExperimentRecord,
) -> int:
    """Return how many cases each candidate was judged on.

    Every observation of one experiment judges the same benchmark, so the
    winner's case count is the experiment's case count.
    """

    return len(experiment.winner.cases)


def _append_observation(
    lines: list[str],
    rank: int,
    observation: WorkflowExperimentObservation,
) -> None:
    """Append one ranked experiment observation."""

    scorecard = observation.scorecard

    cases_passed = observation.cases_passed

    lines.extend(
        (
            "",
            f"Rank {rank}",
            f"Observation ID: {observation.id}",
            f"Workflow: {observation.workflow.name}",
            f"Workflow ID: {observation.workflow.id}",
            "Workflow Revision: "
            + (
                str(observation.candidate_signature.workflow_revision)
                if observation.candidate_signature.workflow_revision is not None
                else "unknown"
            ),
            "Strategy IDs: "
            + ", ".join(
                str(strategy_id) for strategy_id in observation.candidate_signature.strategy_ids
            ),
            (
                f"Passed: {cases_passed}/{len(observation.cases)}"
                if cases_passed is not None
                else "Passed: unknown"
            ),
            *(_render_case(case) for case in observation.cases),
            f"Quality: {scorecard.quality_score:.6f}",
            f"Reliability: {scorecard.reliability_score:.6f}",
            f"Latency: {scorecard.latency_score:.6f}",
            f"Cost: {scorecard.cost_score:.6f}",
            f"Overall: {scorecard.overall_score:.6f}",
        )
    )

    if scorecard.rationale:
        lines.append(f"Rationale: {scorecard.rationale}")


def _render_case(
    case: WorkflowExperimentCaseObservation,
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

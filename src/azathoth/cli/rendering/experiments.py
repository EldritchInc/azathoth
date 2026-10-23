"""Human-readable workflow experiment rendering."""

from collections.abc import Iterable

from azathoth.workflows import (
    WorkflowExperimentObservation,
    WorkflowExperimentRecord,
)


def render_workflow_experiment_summaries(
    experiments: Iterable[WorkflowExperimentRecord],
) -> str:
    """Render one line per experiment in the order given.

    Each line contains the experiment ID, recorded time, candidate count,
    winning run ID, and winning overall score.
    """

    return "\n".join(_render_summary(experiment) for experiment in experiments)


def render_workflow_experiment(
    experiment: WorkflowExperimentRecord,
) -> str:
    """Render one durable experiment with every observation in rank order."""

    lines = [
        f"Experiment ID: {experiment.id}",
        f"Recorded: {experiment.recorded_at.isoformat()}",
        f"Candidates: {len(experiment.observations)}",
        f"Winner Run ID: {experiment.winner.cases[0].run_id}",
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
        f"winner {winner.cases[0].run_id}  overall {winner.scorecard.overall_score:.6f}"
    )


def _append_observation(
    lines: list[str],
    rank: int,
    observation: WorkflowExperimentObservation,
) -> None:
    """Append one ranked experiment observation."""

    scorecard = observation.scorecard

    lines.extend(
        (
            "",
            f"Rank {rank}",
            f"Workflow: {observation.workflow.name}",
            f"Workflow ID: {observation.workflow.id}",
            *(
                line
                for case in observation.cases
                for line in (
                    f"Run ID: {case.run_id}",
                    f"Evaluation ID: {case.evaluation_id}",
                )
            ),
            "Strategy IDs: "
            + ", ".join(
                str(strategy_id) for strategy_id in observation.candidate_signature.strategy_ids
            ),
            f"Quality: {scorecard.quality_score:.6f}",
            f"Reliability: {scorecard.reliability_score:.6f}",
            f"Latency: {scorecard.latency_score:.6f}",
            f"Cost: {scorecard.cost_score:.6f}",
            f"Overall: {scorecard.overall_score:.6f}",
        )
    )

    if scorecard.rationale:
        lines.append(f"Rationale: {scorecard.rationale}")

"""Human-readable workflow optimization rendering."""

from azathoth.optimization import WorkflowOptimizationSession
from azathoth.workflows import (
    WorkflowCandidateSignature,
    WorkflowScorecard,
)


def render_workflow_optimization_session(
    session: WorkflowOptimizationSession,
) -> str:
    """Render one empirical workflow optimization session."""

    initial_workflow = session.initial_candidates[0].metadata

    lines = [
        f"Workflow: {initial_workflow.name}",
        f"Workflow ID: {initial_workflow.id}",
        f"Initial Candidates: {len(session.initial_candidates)}",
        f"Generations: {len(session.generations)}",
    ]

    for result in session.generations:
        experiment = result.previous_experiment
        winner = experiment.winner_evidence

        lines.extend(
            (
                "",
                f"Generation {result.generation}",
                f"Evaluated Candidates: {len(experiment.evidence)}",
                "Winner:",
            )
        )

        _append_candidate_signature(
            lines,
            winner.candidate_signature,
        )

        _append_scorecard(
            lines,
            winner.scorecard,
        )

        lines.append(
            f"Next Population: {len(result.candidates)}",
        )

    return "\n".join(lines)


def _append_candidate_signature(
    lines: list[str],
    signature: WorkflowCandidateSignature,
) -> None:
    """Append deterministic executable candidate identity."""

    lines.append(
        f"  Workflow ID: {signature.workflow_id}",
    )

    lines.append(
        "  Strategy IDs: " + ", ".join(str(strategy_id) for strategy_id in signature.strategy_ids)
    )


def _append_scorecard(
    lines: list[str],
    scorecard: WorkflowScorecard,
) -> None:
    """Append normalized workflow scorecard values."""

    lines.extend(
        (
            f"  Quality: {scorecard.quality_score:.6f}",
            f"  Reliability: {scorecard.reliability_score:.6f}",
            f"  Latency: {scorecard.latency_score:.6f}",
            f"  Cost: {scorecard.cost_score:.6f}",
            f"  Overall: {scorecard.overall_score:.6f}",
        )
    )

"""Human-readable workflow optimization rendering."""

from azathoth.optimization import (
    WorkflowOptimizationSession,
    resolve_workflow_experiment_winner,
)
from azathoth.prompting import (
    ContextPromptStrategy,
    PromptStrategy,
)
from azathoth.strategies import Strategy
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateSignature,
    WorkflowCandidateStep,
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

    evaluated_candidates = tuple(session.initial_candidates)

    for result in session.generations:
        experiment = result.previous_experiment
        winner_evidence = experiment.winner_evidence
        winner = resolve_workflow_experiment_winner(
            experiment=experiment,
            candidates=evaluated_candidates,
        )

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
            winner_evidence.candidate_signature,
        )

        _append_candidate_steps(
            lines,
            winner,
        )

        _append_scorecard(
            lines,
            winner_evidence.scorecard,
        )

        lines.append(
            f"Next Population: {len(result.candidates)}",
        )

        evaluated_candidates = tuple(result.candidates)

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


def _append_candidate_steps(
    lines: list[str],
    candidate: WorkflowCandidate,
) -> None:
    """Append executable step identities and model bindings."""

    for step in candidate.steps:
        lines.append("")

        _append_candidate_step(
            lines,
            step,
        )


def _append_candidate_step(
    lines: list[str],
    step: WorkflowCandidateStep,
) -> None:
    """Append one executable candidate step."""

    strategy = step.strategy

    lines.extend(
        (
            f"  Step: {strategy.metadata.name}",
            f"  Step ID: {step.id}",
            f"  Strategy ID: {strategy.metadata.id}",
        )
    )

    model_identifier = _model_identifier(
        strategy,
    )

    if model_identifier is not None:
        lines.append(
            f"  Model: {model_identifier}",
        )


def _model_identifier(
    strategy: Strategy,
) -> str | None:
    """Return an executable strategy's explicit model binding."""

    if isinstance(
        strategy,
        (
            PromptStrategy,
            ContextPromptStrategy,
        ),
    ):
        binding = strategy.model_binding

        if binding is not None:
            return binding.identifier

    return None


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

"""Human-readable workflow optimization rendering.

`workflow optimize` here renders the session it ran; given `--remote`, it
renders the summary the remote's service API returns, in the same lines
(ADR 0140).
"""

from azathoth import api
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
    WorkflowExperimentResult,
    WorkflowScorecard,
)


def render_workflow_optimization_session(
    session: WorkflowOptimizationSession,
) -> str:
    """Render one empirical workflow optimization session.

    Each generation reports the experiment that measured its population, its
    winner, and the size of the population it proposed. The final evaluation
    (ADR 0091) follows in the same form, or a line saying why it did not run.
    The report ends with the winning experiment's ID, the experiment whose
    winner is the session's winner.

    Judge calls and their cost are reported for the whole session and for
    each experiment, summed over every candidate the experiment evaluated.
    They are the cost of evaluating candidates, never charged to any
    candidate, so they appear beside the scores rather than in them.
    """

    initial_workflow = session.initial_candidates[0].metadata

    experiments = tuple(result.previous_experiment for result in session.generations)

    if session.final_experiment is not None:
        experiments = (*experiments, session.final_experiment)

    lines = [
        f"Workflow: {initial_workflow.name}",
        f"Workflow ID: {initial_workflow.id}",
        f"Initial Candidates: {len(session.initial_candidates)}",
        f"Generations: {len(session.generations)}",
        f"Total Judge Calls: {sum(experiment.judge_calls for experiment in experiments)}",
        f"Total Judge Cost: ${sum(experiment.judge_cost_usd for experiment in experiments):.6f}",
    ]

    evaluated_candidates = tuple(session.initial_candidates)

    for result in session.generations:
        lines.extend(
            (
                "",
                f"Generation {result.generation}",
            )
        )

        _append_experiment(
            lines,
            result.previous_experiment,
            evaluated_candidates,
        )

        lines.append(
            f"Next Population: {len(result.candidates)}",
        )

        evaluated_candidates = tuple(result.candidates)

    if not session.generations:
        return "\n".join(lines)

    lines.append("")

    if session.final_experiment is None:
        last = session.generations[-1].generation

        lines.append(
            f"Final Evaluation: not run. Generation {last} proposed no new candidates, "
            "so its winner is the session's winner."
        )
    else:
        lines.append("Final Evaluation")

        _append_experiment(
            lines,
            session.final_experiment,
            session.final_population,
        )

    winning_experiment = session.winning_experiment

    assert winning_experiment is not None

    lines.extend(
        (
            "",
            f"Winning Experiment ID: {winning_experiment.id}",
        )
    )

    return "\n".join(lines)


def _append_experiment(
    lines: list[str],
    experiment: WorkflowExperimentResult,
    candidates: tuple[WorkflowCandidate, ...],
) -> None:
    """Append one experiment's identity, judging, and winner."""

    winner_evidence = experiment.winner_evidence
    winner = resolve_workflow_experiment_winner(
        experiment=experiment,
        candidates=candidates,
    )

    lines.extend(
        (
            f"Experiment ID: {experiment.id}",
            f"Evaluated Candidates: {len(experiment.evidence)}",
            f"Judge Calls: {experiment.judge_calls}",
            f"Judge Cost: ${experiment.judge_cost_usd:.6f}",
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
            *(
                (f"  Citations: {scorecard.citation_score:.6f}",)
                if scorecard.citation_score is not None
                else ()
            ),
            f"  Overall: {scorecard.overall_score:.6f}",
        )
    )


def render_optimization_summary(
    summary: api.OptimizationSummary,
) -> str:
    """Render a session's summary as `render_workflow_optimization_session` renders the session."""

    lines = [
        f"Workflow: {summary.workflow_name}",
        f"Workflow ID: {summary.workflow_id}",
        f"Initial Candidates: {summary.initial_candidates}",
        f"Generations: {len(summary.generations)}",
        f"Total Judge Calls: {summary.judge_calls}",
        f"Total Judge Cost: ${summary.judge_cost_usd:.6f}",
    ]

    for generation in summary.generations:
        lines.extend(("", f"Generation {generation.generation}"))
        lines.extend(_experiment_lines(generation.experiment))
        lines.append(f"Next Population: {generation.proposed}")

    lines.append("")

    if summary.final_experiment is None:
        lines.append(f"Final Evaluation: not run. {summary.final_skipped}")
    else:
        lines.append("Final Evaluation")
        lines.extend(_experiment_lines(summary.final_experiment))

    lines.extend(("", f"Winning Experiment ID: {summary.winning_experiment_id}"))

    return "\n".join(lines)


def _experiment_lines(
    experiment: api.OptimizationExperiment,
) -> list[str]:
    """Return one experiment's identity, judging, and winner, as `_append_experiment` does."""

    lines = [
        f"Experiment ID: {experiment.experiment_id}",
        f"Evaluated Candidates: {experiment.evaluated}",
        f"Judge Calls: {experiment.judge_calls}",
        f"Judge Cost: ${experiment.judge_cost_usd:.6f}",
        "Winner:",
        f"  Workflow ID: {experiment.winner_workflow_id}",
        "  Strategy IDs: "
        + ", ".join(str(strategy_id) for strategy_id in experiment.winner_strategy_ids),
    ]

    for step in experiment.winner_steps:
        lines.extend(
            (
                "",
                f"  Step: {step.name}",
                f"  Step ID: {step.step_id}",
                f"  Strategy ID: {step.strategy_id}",
                *((f"  Model: {step.model}",) if step.model is not None else ()),
            )
        )

    scorecard = experiment.winner_scorecard

    lines.extend(
        (
            f"  Quality: {scorecard.quality_score:.6f}",
            f"  Reliability: {scorecard.reliability_score:.6f}",
            f"  Latency: {scorecard.latency_score:.6f}",
            f"  Cost: {scorecard.cost_score:.6f}",
            *(
                (f"  Citations: {scorecard.citation_score:.6f}",)
                if scorecard.citation_score is not None
                else ()
            ),
            f"  Overall: {scorecard.overall_score:.6f}",
        )
    )

    return lines

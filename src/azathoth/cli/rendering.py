"""Human-readable rendering for Azathoth CLI results."""

import json

from pydantic import JsonValue

from azathoth.optimization import WorkflowOptimizationSession
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.workflows import (
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    WorkflowCandidateSignature,
    WorkflowProductionRevision,
    WorkflowRun,
    WorkflowScorecard,
    WorkflowStepRun,
    WorkflowStepStatus,
)


def render_production_invocation_result(
    result: ProductionInvocationResult,
) -> str:
    """Render one caller-visible production invocation result."""

    if isinstance(
        result,
        ProductionInvocationSuccess,
    ):
        return "\n".join(
            (
                f"Invocation ID: {result.invocation_id}",
                "Status: succeeded",
                "Result:",
                _render_json_value(result.result),
            )
        )

    assert isinstance(
        result,
        ProductionInvocationFailure,
    )

    lines = [
        f"Invocation ID: {result.invocation_id}",
        "Status: failed",
        f"Error: {result.error_code.value}",
        f"Message: {result.message}",
    ]

    if result.metadata:
        lines.extend(
            (
                "Metadata:",
                _render_json_value(result.metadata),
            )
        )

    return "\n".join(lines)


def render_workflow_promotion(
    revision: WorkflowProductionRevision,
) -> str:
    """Render one completed workflow production promotion."""

    state = revision.state
    workflow = state.specification.metadata

    lines = [
        f"Workflow: {workflow.name}",
        f"Workflow ID: {workflow.id}",
        f"Revision ID: {revision.id}",
        "Status: promoted",
        f"Created At: {revision.created_at.isoformat()}",
    ]

    for step in state.specification.steps:
        specification = step.specification

        if not isinstance(
            specification,
            PromptStrategySpec,
        ):
            continue

        selection = specification.model_selection

        assert isinstance(
            selection,
            FixedModelSelection,
        )

        lines.extend(
            (
                "",
                f"Prompt Step: {step.id}",
                f"Primary Model: {selection.identifier}",
            )
        )

        substitution = next(
            (candidate for candidate in state.model_substitutions if candidate.step_id == step.id),
            None,
        )

        if substitution is not None:
            lines.append(
                "Substitute Models: "
                + ", ".join(model.identifier for model in substitution.substitutes)
            )

    return "\n".join(lines)


def render_workflow_run(
    run: WorkflowRun,
) -> str:
    """Render one completed workflow run for a human operator."""

    statistics = run.statistics

    lines = [
        f"Workflow: {run.workflow.name}",
        f"Workflow ID: {run.workflow.id}",
        f"Run ID: {run.id}",
        (f"Status: {'succeeded' if run.succeeded else 'failed'}"),
        f"Duration: {run.duration_seconds:.3f}s",
        f"Steps: {statistics.total_steps}",
        f"Executed: {statistics.executed_steps}",
        f"Failed: {statistics.failed_steps}",
        f"Skipped: {statistics.skipped_steps}",
        f"Retries: {statistics.retry_count}",
    ]

    for index, step in enumerate(
        run.steps,
        start=1,
    ):
        lines.extend(
            (
                "",
                f"Step {index}",
                f"ID: {step.step_id}",
                f"Status: {step.status.value}",
                f"Attempts: {len(step.attempts)}",
            )
        )

        if step.status is WorkflowStepStatus.EXECUTED:
            _append_execution(
                lines,
                step,
            )

        elif step.status is WorkflowStepStatus.FAILED:
            _append_failure(
                lines,
                step,
            )

    return "\n".join(lines)


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


def _append_execution(
    lines: list[str],
    step: WorkflowStepRun,
) -> None:
    """Append successful execution evidence for one workflow step."""

    execution = step.execution

    assert execution is not None

    lines.append(f"Strategy: {execution.strategy_name}")

    metrics = execution.metrics

    if metrics is not None:
        if metrics.provider is not None:
            lines.append(f"Provider: {metrics.provider}")

        if metrics.model is not None:
            lines.append(f"Model: {metrics.model}")

        if metrics.prompt_tokens is not None:
            lines.append(f"Prompt Tokens: {metrics.prompt_tokens}")

        if metrics.completion_tokens is not None:
            lines.append(f"Completion Tokens: {metrics.completion_tokens}")

        if metrics.total_tokens is not None:
            lines.append(f"Total Tokens: {metrics.total_tokens}")

        if metrics.latency_ms is not None:
            lines.append(f"Latency: {metrics.latency_ms} ms")

        if metrics.estimated_cost_usd is not None:
            lines.append(f"Estimated Cost: ${metrics.estimated_cost_usd:.6f}")

    lines.extend(
        (
            "Output:",
            _render_json_value(execution.output),
        )
    )


def _append_failure(
    lines: list[str],
    step: WorkflowStepRun,
) -> None:
    """Append terminal failure evidence for one workflow step."""

    assert step.attempts

    failure = step.attempts[-1].failure

    assert failure is not None

    lines.append(f"Error: {failure.exception_type}: {failure.message}")


def _render_json_value(
    value: JsonValue,
) -> str:
    """Render one JSON-compatible execution value."""

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )

"""Human-readable workflow run rendering."""

import json

from pydantic import JsonValue

from azathoth.cli.rendering._json import render_json_value
from azathoth.cli.rendering.lineage import render_lineage_lines
from azathoth.cli.rendering.resumes import render_child_count_lines, render_resume_lines
from azathoth.cli.rendering.sensitivity import render_sensitivity_lines
from azathoth.context import context_sensitivity
from azathoth.strategies import StrategyResourceBinding
from azathoth.workflows import (
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStepStatus,
)


def render_workflow_run(
    run: WorkflowRun,
    *,
    resumes: int = 0,
    children: int = 0,
) -> str:
    """Render one completed workflow run for a human operator.

    A run started by a step of another run names its depth, the parent step
    and the root run, right after its ID (ADR 0104). A run that was resumed
    names how often, after its lineage, and one whose steps started children
    names how many (ADR 0105). A run whose label is not internal names it
    right after its ID (ADR 0123).
    """

    statistics = run.statistics

    lines = [
        f"Workflow: {run.workflow.name}",
        f"Workflow ID: {run.workflow.id}",
        f"Workflow Revision: {_render_revision(run.workflow_revision)}",
        f"Run ID: {run.id}",
        *render_sensitivity_lines(context_sensitivity(run.initial_context)),
        *render_lineage_lines(run.initial_context),
        *render_resume_lines(resumes),
        *render_child_count_lines(children),
        f"Status: {'succeeded' if run.succeeded else 'failed'}",
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


def _append_execution(
    lines: list[str],
    step: WorkflowStepRun,
) -> None:
    """Append successful execution evidence for one workflow step.

    A step that recorded a confidence names it after its strategy (ADR 0098).
    """

    execution = step.execution

    assert execution is not None

    lines.append(f"Strategy: {execution.strategy_name}")

    if step.confidence is not None:
        lines.append(f"Confidence: {step.confidence}")

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

    lines.extend(f"Resource: {_render_resource(resource)}" for resource in execution.resources)

    lines.extend(
        (
            "Output:",
            render_json_value(execution.output),
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


def _render_resource(
    resource: StrategyResourceBinding,
) -> str:
    """Render one resource binding with deterministically ordered attributes."""

    rendered = f"{resource.kind} {resource.identifier}"

    if not resource.attributes:
        return rendered

    attributes = ", ".join(
        f"{name}={_render_attribute(resource.attributes[name])}"
        for name in sorted(resource.attributes)
    )

    return f"{rendered} ({attributes})"


def _render_attribute(
    value: JsonValue,
) -> str:
    """Render one resource attribute value compactly."""

    if isinstance(value, str):
        return value

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _render_revision(
    revision: int | None,
) -> str:
    """Render one workflow revision number, or that it is unknown."""

    return str(revision) if revision is not None else "unknown"


__all__ = [
    "render_workflow_run",
]

"""Human-readable rendering for Azathoth CLI results."""

import json

from pydantic import JsonValue

from azathoth.workflows import (
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStepStatus,
)


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

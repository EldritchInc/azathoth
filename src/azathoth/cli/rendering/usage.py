"""Human-readable rendering for workflow resource usage reports.

Each renderer takes the service API's model (ADR 0133), or the workflows'
own report, which it reads as that model first, so both read alike.
"""

from azathoth.api import (
    ModelRunUsage,
    ModelUsage,
    ModelUsageWorkflow,
    ProductionStepUsage,
    ToolRunUsage,
    ToolUsage,
    ToolUsageWorkflow,
)
from azathoth.api.usage import model_usage_of, tool_usage_of
from azathoth.workflows import (
    WorkflowModelUsageReport,
    WorkflowToolUsageReport,
)


def render_model_usage_report(
    report: ModelUsage | WorkflowModelUsageReport,
) -> str:
    """Render where one model is configured, active, and executed."""

    usage = model_usage_of(report) if isinstance(report, WorkflowModelUsageReport) else report

    lines = [
        f"Model: {usage.identifier}",
        f"Workflows: {len(usage.workflows)}",
        f"In Production: {_render_flag(usage.in_production)}",
    ]

    for index, entry in enumerate(
        usage.workflows,
        start=1,
    ):
        _append_model_entry(
            lines,
            index,
            entry,
        )

    return "\n".join(lines)


def render_tool_usage_report(
    report: ToolUsage | WorkflowToolUsageReport,
) -> str:
    """Render where one tool identity is configured, active, and executed."""

    usage = tool_usage_of(report) if isinstance(report, WorkflowToolUsageReport) else report

    lines = [
        f"Tool ID: {usage.tool_id}",
        f"Names: {', '.join(usage.tool_names) if usage.tool_names else 'unknown'}",
        f"Workflows: {len(usage.workflows)}",
        f"In Production: {_render_flag(usage.in_production)}",
    ]

    for index, entry in enumerate(
        usage.workflows,
        start=1,
    ):
        _append_tool_entry(
            lines,
            index,
            entry,
        )

    return "\n".join(lines)


def _append_model_entry(
    lines: list[str],
    index: int,
    entry: ModelUsageWorkflow,
) -> None:
    """Append one workflow's model usage."""

    lines.extend(
        (
            "",
            f"Workflow {index}",
            f"Name: {entry.workflow_name}",
            f"ID: {entry.workflow_id}",
            f"Configured: {_render_flag(entry.configured)}",
            f"Production: {_render_model_production(entry.production)}",
            f"Runs: {len(entry.runs)}",
        )
    )

    lines.extend(_render_model_run(run) for run in entry.runs)


def _append_tool_entry(
    lines: list[str],
    index: int,
    entry: ToolUsageWorkflow,
) -> None:
    """Append one workflow's tool usage."""

    lines.extend(
        (
            "",
            f"Workflow {index}",
            f"Name: {entry.workflow_name}",
            f"ID: {entry.workflow_id}",
            f"Configured: {_render_flag(entry.configured)}",
            f"Production: {_render_flag(entry.production)}",
            f"Runs: {len(entry.runs)}",
        )
    )

    lines.extend(_render_tool_run(run) for run in entry.runs)


def _render_model_production(
    usages: tuple[ProductionStepUsage, ...],
) -> str:
    """Render production roles held by one model."""

    if not usages:
        return "no"

    return ", ".join(f"{usage.role} step {usage.step_id}" for usage in usages)


def _render_model_run(
    run: ModelRunUsage,
) -> str:
    """Render one run's successful executions of a model."""

    executions = ", ".join(
        f"step {usage.step_id} attempt {usage.attempt_number}" for usage in run.steps
    )

    return f"Run {run.run_id} at {run.started_at.isoformat()}: {executions}"


def _render_tool_run(
    run: ToolRunUsage,
) -> str:
    """Render one run's successful executions of a tool."""

    executions = ", ".join(
        (
            f"step {usage.step_id} attempt {usage.attempt_number} "
            f"implementation {usage.implementation_id} "
            f"version {usage.tool_version} runtime {usage.runtime}"
        )
        for usage in run.executions
    )

    return f"Run {run.run_id} at {run.started_at.isoformat()}: {executions}"


def _render_flag(
    value: bool,
) -> str:
    """Render one boolean usage fact."""

    return "yes" if value else "no"

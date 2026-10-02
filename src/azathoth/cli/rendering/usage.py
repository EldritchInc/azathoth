"""Human-readable rendering for workflow resource usage reports."""

from azathoth.workflows import (
    WorkflowModelUsageEntry,
    WorkflowModelUsageReport,
    WorkflowProductionModelUsage,
    WorkflowRunModelUsage,
    WorkflowRunToolUsage,
    WorkflowToolUsageEntry,
    WorkflowToolUsageReport,
)


def render_model_usage_report(
    report: WorkflowModelUsageReport,
) -> str:
    """Render where one model is configured, active, and executed."""

    lines = [
        f"Model: {report.identifier}",
        f"Workflows: {len(report.workflows)}",
        f"In Production: {_render_flag(report.in_production)}",
    ]

    for index, entry in enumerate(
        report.workflows,
        start=1,
    ):
        _append_model_entry(
            lines,
            index,
            entry,
        )

    return "\n".join(lines)


def render_tool_usage_report(
    report: WorkflowToolUsageReport,
) -> str:
    """Render where one tool identity is configured, active, and executed."""

    lines = [
        f"Tool ID: {report.tool_id}",
        f"Names: {', '.join(report.tool_names) if report.tool_names else 'unknown'}",
        f"Workflows: {len(report.workflows)}",
        f"In Production: {_render_flag(report.in_production)}",
    ]

    for index, entry in enumerate(
        report.workflows,
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
    entry: WorkflowModelUsageEntry,
) -> None:
    """Append one workflow's model usage."""

    lines.extend(
        (
            "",
            f"Workflow {index}",
            f"Name: {entry.workflow.name}",
            f"ID: {entry.workflow.id}",
            f"Configured: {_render_flag(entry.configured)}",
            f"Production: {_render_model_production(entry.production)}",
            f"Runs: {len(entry.runs)}",
        )
    )

    lines.extend(_render_model_run(run) for run in entry.runs)


def _append_tool_entry(
    lines: list[str],
    index: int,
    entry: WorkflowToolUsageEntry,
) -> None:
    """Append one workflow's tool usage."""

    lines.extend(
        (
            "",
            f"Workflow {index}",
            f"Name: {entry.workflow.name}",
            f"ID: {entry.workflow.id}",
            f"Configured: {_render_flag(entry.configured)}",
            f"Production: {_render_flag(entry.in_production)}",
            f"Runs: {len(entry.runs)}",
        )
    )

    lines.extend(_render_tool_run(run) for run in entry.runs)


def _render_model_production(
    usages: tuple[WorkflowProductionModelUsage, ...],
) -> str:
    """Render production roles held by one model."""

    if not usages:
        return "no"

    return ", ".join(f"{usage.role.value} step {usage.step_id}" for usage in usages)


def _render_model_run(
    run: WorkflowRunModelUsage,
) -> str:
    """Render one run's successful executions of a model."""

    executions = ", ".join(
        f"step {usage.step_id} attempt {usage.attempt_number}" for usage in run.usages
    )

    return f"Run {run.run_id} at {run.started_at.isoformat()}: {executions}"


def _render_tool_run(
    run: WorkflowRunToolUsage,
) -> str:
    """Render one run's successful executions of a tool."""

    executions = ", ".join(
        (
            f"step {usage.step_id} attempt {usage.attempt_number} "
            f"implementation {usage.implementation_id} "
            f"version {usage.tool_version} runtime {usage.runtime}"
        )
        for usage in run.usages
    )

    return f"Run {run.run_id} at {run.started_at.isoformat()}: {executions}"


def _render_flag(
    value: bool,
) -> str:
    """Render one boolean usage fact."""

    return "yes" if value else "no"

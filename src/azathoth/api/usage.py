"""Where a model or a tool is used, through the service API (ADR 0133).

The reports are the workflows' own (`model_usage_report` and
`tool_usage_report`); these turn them into the API's models, so the
command line's `model usage` and `tool usage` and every other caller read
the same thing.
"""

from azathoth.api.models import (
    ModelRunUsage,
    ModelUsage,
    ModelUsageWorkflow,
    ProductionStepUsage,
    StepAttemptUsage,
    ToolExecutionUsage,
    ToolRunUsage,
    ToolUsage,
    ToolUsageWorkflow,
)
from azathoth.workflows import (
    WorkflowModelUsageReport,
    WorkflowProductionModelUsageRole,
    WorkflowToolUsageReport,
)


def model_usage_of(report: WorkflowModelUsageReport) -> ModelUsage:
    """Return a model's usage report as the API's model."""

    return ModelUsage(
        identifier=report.identifier,
        in_production=report.in_production,
        workflows=tuple(
            ModelUsageWorkflow(
                workflow_id=entry.workflow.id,
                workflow_name=entry.workflow.name,
                configured=entry.configured,
                production=tuple(
                    ProductionStepUsage(
                        step_id=usage.step_id,
                        role=(
                            "primary"
                            if usage.role is WorkflowProductionModelUsageRole.PRIMARY
                            else "substitute"
                        ),
                    )
                    for usage in entry.production
                ),
                runs=tuple(
                    ModelRunUsage(
                        run_id=run.run_id,
                        started_at=run.started_at,
                        steps=tuple(
                            StepAttemptUsage(
                                step_id=usage.step_id, attempt_number=usage.attempt_number
                            )
                            for usage in run.usages
                        ),
                    )
                    for run in entry.runs
                ),
            )
            for entry in report.workflows
        ),
    )


def tool_usage_of(report: WorkflowToolUsageReport) -> ToolUsage:
    """Return a tool's usage report as the API's model."""

    return ToolUsage(
        tool_id=report.tool_id,
        tool_names=report.tool_names,
        in_production=report.in_production,
        workflows=tuple(
            ToolUsageWorkflow(
                workflow_id=entry.workflow.id,
                workflow_name=entry.workflow.name,
                configured=entry.configured,
                production=entry.in_production,
                runs=tuple(
                    ToolRunUsage(
                        run_id=run.run_id,
                        started_at=run.started_at,
                        executions=tuple(
                            ToolExecutionUsage(
                                step_id=usage.step_id,
                                attempt_number=usage.attempt_number,
                                implementation_id=usage.implementation_id,
                                tool_version=usage.tool_version,
                                runtime=usage.runtime,
                            )
                            for usage in run.usages
                        ),
                    )
                    for run in entry.runs
                ),
            )
            for entry in report.workflows
        ),
    )


__all__ = [
    "model_usage_of",
    "tool_usage_of",
]

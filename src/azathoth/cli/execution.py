"""Application services for executing configured workflows."""

from uuid import UUID

from azathoth.context import Context
from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    WorkflowRun,
    WorkflowRunner,
)


async def execute_configured_workflow(
    *,
    runtime: RuntimeEnvironment,
    workflow_id: UUID,
    context: Context | None = None,
    runner: WorkflowRunner | None = None,
) -> WorkflowRun:
    """Generate and execute one configured workflow."""

    candidate = runtime.generate_workflow_candidate(workflow_id)

    workflow_runner = runner if runner is not None else WorkflowRunner()

    execution_context = context if context is not None else Context()

    return await workflow_runner.run(
        candidate,
        execution_context,
    )

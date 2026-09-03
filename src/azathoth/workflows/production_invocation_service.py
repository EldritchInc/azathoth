"""Application service for invoking active production workflows."""

from collections.abc import Mapping
from uuid import UUID

from pydantic import JsonValue

from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.tools import (
    ToolImplementationResolver,
    ToolResolver,
)
from azathoth.workflows.production import WorkflowProductionState
from azathoth.workflows.production_execution import (
    complete_production_invocation,
)
from azathoth.workflows.production_invocation import (
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    create_production_invocation,
)
from azathoth.workflows.production_invocation_repository import (
    ProductionInvocationRepository,
)
from azathoth.workflows.production_invocation_run_repository import (
    ProductionInvocationRunRepository,
)
from azathoth.workflows.run_repository import WorkflowRunRepository
from azathoth.workflows.runner import WorkflowRunner


async def invoke_production_workflow(
    *,
    workflow_id: UUID,
    payload: JsonValue,
    production_state: WorkflowProductionState | None,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    invocation_repository: ProductionInvocationRepository,
    run_repository: WorkflowRunRepository,
    invocation_run_repository: ProductionInvocationRunRepository,
    caller_metadata: Mapping[str, JsonValue] | None = None,
    runner: WorkflowRunner | None = None,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
) -> ProductionInvocationResult:
    """Invoke one workflow against its active production state."""

    invocation = create_production_invocation(
        workflow_id=workflow_id,
        payload=payload,
        caller_metadata=caller_metadata,
    )

    invocation_repository.save(
        invocation,
    )

    if production_state is None:
        result: ProductionInvocationResult = ProductionInvocationFailure(
            invocation_id=invocation.id,
            error_code=ProductionInvocationErrorCode.WORKFLOW_NOT_DEPLOYED,
            message="The requested workflow is not deployed to production.",
        )

        invocation_repository.save_result(
            result,
        )

        return result

    if production_state.specification.metadata.id != workflow_id:
        result = ProductionInvocationFailure(
            invocation_id=invocation.id,
            error_code=ProductionInvocationErrorCode.WORKFLOW_NOT_DEPLOYED,
            message="The requested workflow is not deployed to production.",
        )

        invocation_repository.save_result(
            result,
        )

        return result

    return await complete_production_invocation(
        invocation=invocation,
        state=production_state,
        catalog=catalog,
        registry=registry,
        runner=runner if runner is not None else WorkflowRunner(),
        run_repository=run_repository,
        invocation_repository=invocation_repository,
        invocation_run_repository=invocation_run_repository,
        tool_resolver=tool_resolver,
        tool_implementation_resolver=tool_implementation_resolver,
    )

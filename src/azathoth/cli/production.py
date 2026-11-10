"""Application services for invoking active production workflows."""

from collections.abc import Mapping
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import WorkflowLineage
from azathoth.inputs import InputProvenance
from azathoth.runtime import AzathothRuntime
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import (
    InvocationIdempotency,
    ProductionInvocationRepository,
    ProductionInvocationResult,
    ProductionInvocationRunRepository,
    WorkflowRunner,
    WorkflowRunRepository,
    invoke_production_workflow,
)


async def invoke_active_production_workflow(
    *,
    runtime: AzathothRuntime,
    workflow_id: UUID,
    payload: JsonValue,
    invocation_repository: ProductionInvocationRepository,
    run_repository: WorkflowRunRepository,
    invocation_run_repository: ProductionInvocationRunRepository,
    caller_metadata: Mapping[str, JsonValue] | None = None,
    runner: WorkflowRunner | None = None,
    input_provenance: InputProvenance | None = None,
    idempotency: InvocationIdempotency | None = None,
    lineage: WorkflowLineage | None = None,
    sensitivity: Sensitivity | None = None,
) -> ProductionInvocationResult:
    """Invoke the active production state for one workflow.

    An invocation started by a step of another run records its lineage
    (ADR 0104), and one given a labelled input its label (ADR 0123).

    Raises:
        IdempotencyKeyInUseError: The idempotency key is already recorded on
            another invocation. Nothing is saved and nothing runs.
    """

    return await invoke_production_workflow(
        workflow_id=workflow_id,
        payload=payload,
        caller_metadata=caller_metadata,
        production_state=runtime.production_state(
            workflow_id,
        ),
        catalog=runtime.models,
        registry=runtime.language_models,
        invocation_repository=invocation_repository,
        run_repository=run_repository,
        invocation_run_repository=invocation_run_repository,
        runner=runner,
        tool_resolver=runtime.tool_resolver,
        tool_implementation_resolver=runtime.tool_implementation_resolver,
        input_provenance=input_provenance,
        idempotency=idempotency,
        lineage=lineage,
        sensitivity=sensitivity,
    )

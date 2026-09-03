"""Execute production workflow invocations."""

from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.tools import (
    ToolImplementationResolver,
    ToolResolver,
)
from azathoth.workflows.execution import WorkflowRun
from azathoth.workflows.production import WorkflowProductionRevision
from azathoth.workflows.production_generation import (
    generate_production_workflow_candidate,
)
from azathoth.workflows.production_invocation import (
    ProductionInvocation,
)
from azathoth.workflows.production_invocation_run import (
    ProductionInvocationRun,
)
from azathoth.workflows.production_invocation_run_repository import (
    ProductionInvocationRunRepository,
)
from azathoth.workflows.run_repository import WorkflowRunRepository
from azathoth.workflows.runner import WorkflowRunner


async def execute_production_invocation(
    *,
    invocation: ProductionInvocation,
    revision: WorkflowProductionRevision,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    runner: WorkflowRunner,
    run_repository: WorkflowRunRepository,
    invocation_run_repository: ProductionInvocationRunRepository,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
) -> WorkflowRun:
    """Execute one production invocation against its exact revision."""

    _validate_invocation_revision(
        invocation=invocation,
        revision=revision,
    )

    candidate = generate_production_workflow_candidate(
        state=revision.state,
        catalog=catalog,
        registry=registry,
        tool_resolver=tool_resolver,
        tool_implementation_resolver=tool_implementation_resolver,
    )

    run = await runner.run(
        workflow=candidate,
        context=invocation.initial_context,
    )

    run_repository.save(
        run,
    )

    invocation_run_repository.save(
        ProductionInvocationRun(
            invocation_id=invocation.id,
            run_id=run.id,
        )
    )

    return run


def _validate_invocation_revision(
    *,
    invocation: ProductionInvocation,
    revision: WorkflowProductionRevision,
) -> None:
    """Require invocation identity to match the supplied production revision."""

    if invocation.production_revision_id != revision.id:
        raise ValueError(
            "Production invocation does not reference the supplied production revision."
        )

    if invocation.workflow_id != revision.workflow_id:
        raise ValueError(
            "Production invocation workflow does not match the supplied production revision."
        )

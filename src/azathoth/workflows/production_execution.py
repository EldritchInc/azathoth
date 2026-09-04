"""Execute and complete production workflow invocations."""

from pydantic import JsonValue

from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.tools import (
    ToolImplementationResolver,
    ToolResolver,
)
from azathoth.workflows.execution import WorkflowRun
from azathoth.workflows.generation import WorkflowGenerationError
from azathoth.workflows.production import WorkflowProductionState
from azathoth.workflows.production_generation import (
    generate_production_workflow_candidate,
)
from azathoth.workflows.production_invocation import (
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
)
from azathoth.workflows.production_invocation_repository import (
    ProductionInvocationRepository,
)
from azathoth.workflows.production_invocation_run import (
    ProductionInvocationRun,
)
from azathoth.workflows.production_invocation_run_repository import (
    ProductionInvocationRunRepository,
)
from azathoth.workflows.production_model_resolution import (
    ProductionModelSubstitutesUnavailableError,
    ProductionPrimaryModelUnavailableError,
)
from azathoth.workflows.run_repository import WorkflowRunRepository
from azathoth.workflows.runner import WorkflowRunner


class ProductionEmissionError(RuntimeError):
    """Raised when a declared production emission cannot be produced."""


async def execute_production_invocation(
    *,
    invocation: ProductionInvocation,
    state: WorkflowProductionState,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    runner: WorkflowRunner,
    run_repository: WorkflowRunRepository,
    invocation_run_repository: ProductionInvocationRunRepository,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
) -> WorkflowRun:
    """Execute one production invocation against current production state."""

    _validate_invocation_state(
        invocation=invocation,
        state=state,
    )

    candidate = generate_production_workflow_candidate(
        state=state,
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


async def complete_production_invocation(
    *,
    invocation: ProductionInvocation,
    state: WorkflowProductionState,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    runner: WorkflowRunner,
    run_repository: WorkflowRunRepository,
    invocation_repository: ProductionInvocationRepository,
    invocation_run_repository: ProductionInvocationRunRepository,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
) -> ProductionInvocationResult:
    """Execute one invocation and persist its caller-visible terminal result."""

    try:
        run = await execute_production_invocation(
            invocation=invocation,
            state=state,
            catalog=catalog,
            registry=registry,
            runner=runner,
            run_repository=run_repository,
            invocation_run_repository=invocation_run_repository,
            tool_resolver=tool_resolver,
            tool_implementation_resolver=tool_implementation_resolver,
        )

        if run.failed:
            result: ProductionInvocationResult = ProductionInvocationFailure(
                invocation_id=invocation.id,
                error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
                message="Production workflow execution failed.",
            )
        else:
            try:
                emitted = emit_production_result(
                    state=state,
                    run=run,
                )
            except ProductionEmissionError:
                result = ProductionInvocationFailure(
                    invocation_id=invocation.id,
                    error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
                    message="Production workflow did not produce its declared result.",
                )
            else:
                result = ProductionInvocationSuccess(
                    invocation_id=invocation.id,
                    result=emitted,
                )

    except ProductionPrimaryModelUnavailableError:
        result = ProductionInvocationFailure(
            invocation_id=invocation.id,
            error_code=ProductionInvocationErrorCode.MODEL_UNAVAILABLE,
            message="The production model is unavailable.",
        )

    except ProductionModelSubstitutesUnavailableError:
        result = ProductionInvocationFailure(
            invocation_id=invocation.id,
            error_code=ProductionInvocationErrorCode.NO_APPROVED_MODEL_SUBSTITUTE,
            message="No approved production model substitute is available.",
        )

    except WorkflowGenerationError:
        result = ProductionInvocationFailure(
            invocation_id=invocation.id,
            error_code=ProductionInvocationErrorCode.TOOL_UNAVAILABLE,
            message="A required production workflow capability is unavailable.",
        )

    except Exception:
        result = ProductionInvocationFailure(
            invocation_id=invocation.id,
            error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
            message="Production workflow execution failed.",
        )

    invocation_repository.save_result(
        result,
    )

    return result


def emit_production_result(
    *,
    state: WorkflowProductionState,
    run: WorkflowRun,
) -> dict[str, JsonValue]:
    """Return only workflow values explicitly exposed by production policy."""

    result: dict[
        str,
        JsonValue,
    ] = {}

    for emission in state.emissions:
        matches = tuple(
            value
            for value in run.values_from(emission.source.producer_step_id)
            if value.name == emission.source.name
        )

        if len(matches) != 1:
            raise ProductionEmissionError("Declared production emission was not produced uniquely.")

        result[emission.name] = matches[0].value

    return result


def _validate_invocation_state(
    *,
    invocation: ProductionInvocation,
    state: WorkflowProductionState,
) -> None:
    """Require invocation workflow identity to match production state."""

    if invocation.workflow_id != state.specification.metadata.id:
        raise ValueError(
            "Production invocation workflow does not match the supplied production state."
        )

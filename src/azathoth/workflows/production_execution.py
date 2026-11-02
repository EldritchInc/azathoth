"""Execute and complete production workflow invocations."""

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
from azathoth.workflows.references import (
    reference_producer_step_ids,
    resolve_named_value,
)
from azathoth.workflows.run_journal import RunJournalError
from azathoth.workflows.run_lease import RunLeaseError
from azathoth.workflows.run_repository import WorkflowRunRepository
from azathoth.workflows.run_resume import RunResumeError
from azathoth.workflows.runner import WorkflowRunner
from azathoth.workflows.value import WorkflowValueReference


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
    resume_run_id: UUID | None = None,
) -> WorkflowRun:
    """Execute one production invocation against current production state.

    A step failure never escapes as an exception: the completed run, failed or
    not, is persisted and associated with the invocation before it is
    returned, so every executed invocation leaves inspectable evidence.

    The run names the invocation, so a runner that journals its runs records
    which invocation each executes (ADR 0105).

    With `resume_run_id`, the invocation's unfinished run is resumed from its
    journal instead of starting a new one. The state must be the one the run
    started from. A run already recorded, or already associated, is not
    recorded again.

    Raises:
        RunResumeError: The run cannot be resumed with this state, or it
            executes another invocation.
        RunLeaseHeldError: Another process holds the run's live lease.
        RunJournalError: The run's journal could not be recorded, or its
            lease was lost. The invocation stays incomplete.
    """

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

    if resume_run_id is None:
        run = await runner.run_recording_failures(
            candidate,
            invocation.initial_context,
            invocation_id=invocation.id,
        )
    else:
        run = await runner.resume(
            candidate,
            run_id=resume_run_id,
            invocation_id=invocation.id,
        )

    if run_repository.get(run.id) is None:
        run_repository.save(
            run,
        )

    if invocation_run_repository.get(invocation.id) is None:
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
    resume_run_id: UUID | None = None,
) -> ProductionInvocationResult:
    """Execute one invocation and persist its caller-visible terminal result.

    With `resume_run_id`, its unfinished run is resumed instead (ADR 0105).

    A run that stops before it finishes, because its journal could not be
    recorded or its lease was lost, or that cannot be resumed, records no
    result: the error is raised, and the invocation stays incomplete, so it
    can be resumed.

    Raises:
        RunResumeError: The run cannot be resumed with this state.
        RunLeaseError: Another process holds the run's live lease.
        RunJournalError: The run stopped before it finished.
    """

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
            resume_run_id=resume_run_id,
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

    except (RunJournalError, RunLeaseError, RunResumeError):
        raise

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
    """Return only workflow values explicitly exposed by production policy.

    An emission naming its value alone resolves to the first step, in the
    promoted specification's step order, that produced it.

    Raises:
        ProductionEmissionError: An explicit emission was not produced exactly
            once, or a name-only emission was not produced by any step.
    """

    result: dict[
        str,
        JsonValue,
    ] = {}

    for emission in state.emissions:
        source = emission.source

        if not isinstance(
            source,
            WorkflowValueReference,
        ):
            value = resolve_named_value(
                source.name,
                producer_step_ids=reference_producer_step_ids(
                    source,
                    state.specification.steps,
                ),
                values=run.values,
            )

            if value is None:
                raise ProductionEmissionError(
                    "Declared production emission was not produced uniquely."
                )

            result[emission.name] = value.value

            continue

        matches = tuple(
            value for value in run.values_from(source.producer_step_id) if value.name == source.name
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

"""Tests for active production workflow invocation application services."""

import asyncio
from uuid import UUID

from azathoth.cli import invoke_active_production_workflow
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    InMemoryProductionInvocationRepository,
    InMemoryProductionInvocationRunRepository,
    InMemoryWorkflowRunRepository,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNDEPLOYED_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

MODEL = FixedModelSelection(
    provider="test-provider",
    model="production-model",
)


def create_production_state() -> WorkflowProductionState:
    """Create one deterministic active production workflow."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="production workflow",
                description="Exercise CLI production invocation composition.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="production prompt",
                            description="Return deterministic production output.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Return success.",
                        ),
                        model_selection=MODEL,
                    ),
                ),
            ),
        )
    )


def create_runtime(
    *,
    production_states: tuple[WorkflowProductionState, ...] | None = None,
) -> AzathothRuntime:
    """Create deterministic runtime production dependencies."""

    states = production_states if production_states is not None else (create_production_state(),)

    return AzathothRuntime(
        workflows=WorkflowCatalog(),
        production_states=states,
        models=ModelCatalog(
            models=(
                ModelMetadata(
                    provider=MODEL.provider,
                    model=MODEL.model,
                    display_name="Production Model",
                    context_window_tokens=8_192,
                ),
            )
        ),
        portfolio=ModelPortfolio(),
        language_models=LanguageModelRegistry(
            models={
                MODEL.identifier: DeterministicLanguageModel(
                    provider=MODEL.provider,
                    model=MODEL.model,
                    response_text="success",
                ),
            }
        ),
    )


def test_invoke_active_production_workflow_executes_runtime_state() -> None:
    runtime = create_runtime()

    invocation_repository = InMemoryProductionInvocationRepository()

    run_repository = InMemoryWorkflowRunRepository()

    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    result = asyncio.run(
        invoke_active_production_workflow(
            runtime=runtime,
            workflow_id=WORKFLOW_ID,
            payload={
                "message": "hello",
            },
            invocation_repository=invocation_repository,
            run_repository=run_repository,
            invocation_run_repository=invocation_run_repository,
        )
    )

    assert isinstance(
        result,
        ProductionInvocationSuccess,
    )

    invocations = invocation_repository.invocations()

    assert len(invocations) == 1

    invocation = invocations[0]

    assert invocation.workflow_id == WORKFLOW_ID

    association = invocation_run_repository.get(
        invocation.id,
    )

    assert association is not None

    run = run_repository.get(
        association.run_id,
    )

    assert run is not None
    assert run.workflow.id == WORKFLOW_ID

    execution = run.steps[0].execution

    assert execution is not None
    assert execution.output == "success"

    assert (
        invocation_repository.result(
            invocation.id,
        )
        == result
    )


def test_invoke_active_production_workflow_preserves_caller_metadata() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    result = asyncio.run(
        invoke_active_production_workflow(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            payload="hello",
            caller_metadata={
                "request_id": "request-123",
                "tenant_id": "tenant-456",
            },
            invocation_repository=invocation_repository,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
        )
    )

    assert isinstance(
        result,
        ProductionInvocationSuccess,
    )

    invocation = invocation_repository.invocations()[0]

    assert invocation.caller_metadata == {
        "request_id": "request-123",
        "tenant_id": "tenant-456",
    }


def test_invoke_active_production_workflow_records_not_deployed_failure() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    run_repository = InMemoryWorkflowRunRepository()

    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    result = asyncio.run(
        invoke_active_production_workflow(
            runtime=create_runtime(
                production_states=(),
            ),
            workflow_id=UNDEPLOYED_WORKFLOW_ID,
            payload={
                "message": "hello",
            },
            invocation_repository=invocation_repository,
            run_repository=run_repository,
            invocation_run_repository=invocation_run_repository,
        )
    )

    assert isinstance(
        result,
        ProductionInvocationFailure,
    )

    assert result.error_code is ProductionInvocationErrorCode.WORKFLOW_NOT_DEPLOYED

    invocations = invocation_repository.invocations()

    assert len(invocations) == 1

    invocation = invocations[0]

    assert invocation.workflow_id == UNDEPLOYED_WORKFLOW_ID

    assert (
        invocation_repository.result(
            invocation.id,
        )
        == result
    )

    assert run_repository.runs() == ()

    assert invocation_run_repository.associations() == ()

"""Tests for invoking active production workflows."""

import asyncio
from uuid import UUID

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    InMemoryProductionInvocationRepository,
    InMemoryProductionInvocationRunRepository,
    InMemoryWorkflowRunRepository,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    invoke_production_workflow,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

OTHER_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="production-model",
)


def create_state(
    *,
    workflow_id: UUID = WORKFLOW_ID,
) -> WorkflowProductionState:
    """Create deterministic active production state."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=workflow_id,
                name="production-service",
                description="Exercise active production invocation.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="production-prompt",
                            description="Exercise production invocation.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Process the production request.",
                        ),
                        model_selection=PRIMARY,
                    ),
                ),
            ),
        )
    )


def create_catalog() -> ModelCatalog:
    """Create current production model metadata."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider=PRIMARY.provider,
                model=PRIMARY.model,
                display_name=PRIMARY.identifier,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable production model registry."""

    return LanguageModelRegistry(
        {
            PRIMARY.identifier: DeterministicLanguageModel(
                provider=PRIMARY.provider,
                model=PRIMARY.model,
            ),
        }
    )


def test_invoke_production_workflow_creates_and_persists_invocation() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload={
                "request": "hello",
            },
            production_state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            invocation_repository=invocation_repository,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
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

    assert invocation.initial_context.events[0].payload == {
        "input": {
            "request": "hello",
        },
    }

    assert invocation_repository.result(invocation.id) == result


def test_invoke_production_workflow_preserves_caller_metadata() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload="hello",
            caller_metadata={
                "request_id": "request-123",
                "tenant_id": "tenant-456",
            },
            production_state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            invocation_repository=invocation_repository,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
        )
    )

    invocation = invocation_repository.invocations()[0]

    assert invocation.caller_metadata == {
        "request_id": "request-123",
        "tenant_id": "tenant-456",
    }


def test_invoke_production_workflow_executes_active_state() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    run_repository = InMemoryWorkflowRunRepository()

    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload="hello",
            production_state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            invocation_repository=invocation_repository,
            run_repository=run_repository,
            invocation_run_repository=invocation_run_repository,
        )
    )

    assert isinstance(
        result,
        ProductionInvocationSuccess,
    )

    invocation = invocation_repository.invocations()[0]

    association = invocation_run_repository.get(
        invocation.id,
    )

    assert association is not None

    run = run_repository.get(
        association.run_id,
    )

    assert run is not None
    assert run.workflow.id == WORKFLOW_ID
    assert run.initial_context == invocation.initial_context


def test_invoke_production_workflow_returns_not_deployed_without_state() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    run_repository = InMemoryWorkflowRunRepository()

    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload="hello",
            production_state=None,
            catalog=create_catalog(),
            registry=create_registry(),
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

    invocation = invocation_repository.invocations()[0]

    assert result.invocation_id == invocation.id
    assert invocation_repository.result(invocation.id) == result

    assert run_repository.runs() == ()
    assert invocation_run_repository.associations() == ()


def test_invoke_production_workflow_rejects_state_for_different_workflow() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    run_repository = InMemoryWorkflowRunRepository()

    invocation_run_repository = InMemoryProductionInvocationRunRepository()

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload="hello",
            production_state=create_state(
                workflow_id=OTHER_WORKFLOW_ID,
            ),
            catalog=create_catalog(),
            registry=create_registry(),
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

    assert run_repository.runs() == ()
    assert invocation_run_repository.associations() == ()


def test_invoke_production_workflow_records_one_terminal_result() -> None:
    invocation_repository = InMemoryProductionInvocationRepository()

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload="hello",
            production_state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            invocation_repository=invocation_repository,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
        )
    )

    invocation = invocation_repository.invocations()[0]

    assert invocation_repository.result(invocation.id) == result

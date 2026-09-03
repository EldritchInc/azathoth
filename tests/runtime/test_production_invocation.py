"""Tests for invoking production workflows from runtime composition."""

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
    invoke_production_workflow,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNDEPLOYED_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="production-model",
)


def create_state() -> WorkflowProductionState:
    """Create deterministic active production state."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="runtime-production",
                description="Exercise production through runtime state.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="runtime-production-prompt",
                            description="Exercise active runtime production.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Process production input.",
                        ),
                        model_selection=PRIMARY,
                    ),
                ),
            ),
        )
    )


def create_runtime() -> AzathothRuntime:
    """Create runtime containing one active production workflow."""

    models = ModelCatalog(
        models=(
            ModelMetadata(
                provider=PRIMARY.provider,
                model=PRIMARY.model,
                display_name=PRIMARY.identifier,
            ),
        )
    )

    return AzathothRuntime(
        workflows=WorkflowCatalog(),
        production_states=(create_state(),),
        models=models,
        portfolio=ModelPortfolio(),
        language_models=LanguageModelRegistry(
            {
                PRIMARY.identifier: DeterministicLanguageModel(
                    provider=PRIMARY.provider,
                    model=PRIMARY.model,
                ),
            }
        ),
    )


def test_runtime_state_drives_production_invocation() -> None:
    runtime = create_runtime()

    invocation_repository = InMemoryProductionInvocationRepository()

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload={
                "request": "hello",
            },
            production_state=runtime.production_state(
                WORKFLOW_ID,
            ),
            catalog=runtime.models,
            registry=runtime.language_models,
            invocation_repository=invocation_repository,
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
            tool_resolver=runtime.tool_resolver,
            tool_implementation_resolver=runtime.tool_implementation_resolver,
        )
    )

    assert isinstance(
        result,
        ProductionInvocationSuccess,
    )

    assert invocation_repository.invocations()[0].workflow_id == WORKFLOW_ID


def test_missing_runtime_production_state_returns_not_deployed() -> None:
    runtime = create_runtime()

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=UNDEPLOYED_WORKFLOW_ID,
            payload="hello",
            production_state=runtime.production_state(
                UNDEPLOYED_WORKFLOW_ID,
            ),
            catalog=runtime.models,
            registry=runtime.language_models,
            invocation_repository=InMemoryProductionInvocationRepository(),
            run_repository=InMemoryWorkflowRunRepository(),
            invocation_run_repository=InMemoryProductionInvocationRunRepository(),
            tool_resolver=runtime.tool_resolver,
            tool_implementation_resolver=runtime.tool_implementation_resolver,
        )
    )

    assert isinstance(
        result,
        ProductionInvocationFailure,
    )

    assert result.error_code is ProductionInvocationErrorCode.WORKFLOW_NOT_DEPLOYED

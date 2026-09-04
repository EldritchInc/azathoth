"""End-to-end tests for invoking replaced active production state."""

import asyncio
from pathlib import Path
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
    ProductionInvocationSuccess,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRunRepository,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowProductionRevision,
    WorkflowProductionState,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    invoke_production_workflow,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

REVISION_A_ID = UUID("44444444-4444-4444-4444-444444444444")

REVISION_B_ID = UUID("55555555-5555-5555-5555-555555555555")

MODEL_A = FixedModelSelection(
    provider="test-provider",
    model="model-a",
)

MODEL_B = FixedModelSelection(
    provider="test-provider",
    model="model-b",
)


def create_state(
    *,
    selection: FixedModelSelection,
) -> WorkflowProductionState:
    """Create active production state with one exact model selection."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="production-state-replacement",
                description="Prove active production state replacement.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="production-prompt",
                            description="Exercise active production state.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Return the active production model response.",
                        ),
                        model_selection=selection,
                    ),
                ),
            ),
        )
    )


def create_catalog() -> ModelCatalog:
    """Create current metadata containing both production models."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider=MODEL_A.provider,
                model=MODEL_A.model,
                display_name=MODEL_A.identifier,
            ),
            ModelMetadata(
                provider=MODEL_B.provider,
                model=MODEL_B.model,
                display_name=MODEL_B.identifier,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable implementations for both production models."""

    return LanguageModelRegistry(
        {
            MODEL_A.identifier: DeterministicLanguageModel(
                provider=MODEL_A.provider,
                model=MODEL_A.model,
                response_text="state-a",
            ),
            MODEL_B.identifier: DeterministicLanguageModel(
                provider=MODEL_B.provider,
                model=MODEL_B.model,
                response_text="state-b",
            ),
        }
    )


def create_runtime(
    *,
    state: WorkflowProductionState,
) -> AzathothRuntime:
    """Create one process-local runtime snapshot."""

    return AzathothRuntime(
        workflows=WorkflowCatalog(),
        production_states=(state,),
        models=create_catalog(),
        portfolio=ModelPortfolio(),
        language_models=create_registry(),
    )


def invoke(
    *,
    runtime: AzathothRuntime,
    invocation_repository: SQLiteProductionInvocationRepository,
    run_repository: SQLiteWorkflowRunRepository,
    invocation_run_repository: SQLiteProductionInvocationRunRepository,
) -> ProductionInvocationSuccess:
    """Invoke the active workflow represented by one runtime snapshot."""

    result = asyncio.run(
        invoke_production_workflow(
            workflow_id=WORKFLOW_ID,
            payload={
                "request": "execute active production",
            },
            production_state=runtime.production_state(
                WORKFLOW_ID,
            ),
            catalog=runtime.models,
            registry=runtime.language_models,
            invocation_repository=invocation_repository,
            run_repository=run_repository,
            invocation_run_repository=invocation_run_repository,
            runner=WorkflowRunner(),
            tool_resolver=runtime.tool_resolver,
            tool_implementation_resolver=runtime.tool_implementation_resolver,
        )
    )

    assert isinstance(
        result,
        ProductionInvocationSuccess,
    )

    return result


def test_production_invocation_follows_replaced_active_state(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    state_repository = SQLiteWorkflowProductionStateRepository(
        database,
    )

    revision_repository = SQLiteWorkflowProductionRevisionRepository(
        database,
    )

    invocation_repository = SQLiteProductionInvocationRepository(
        database,
    )

    run_repository = SQLiteWorkflowRunRepository(
        database,
    )

    invocation_run_repository = SQLiteProductionInvocationRunRepository(
        database,
    )

    state_a = create_state(
        selection=MODEL_A,
    )

    revision_a = WorkflowProductionRevision(
        id=REVISION_A_ID,
        state=state_a,
    )

    revision_repository.save(
        revision_a,
    )

    state_repository.set(
        state_a,
    )

    persisted_state_a = state_repository.get(
        WORKFLOW_ID,
    )

    assert persisted_state_a is not None

    runtime_a = create_runtime(
        state=persisted_state_a,
    )

    result_a = invoke(
        runtime=runtime_a,
        invocation_repository=invocation_repository,
        run_repository=run_repository,
        invocation_run_repository=invocation_run_repository,
    )

    invocation_a = invocation_repository.invocations()[0]

    association_a = invocation_run_repository.get(
        invocation_a.id,
    )

    assert association_a is not None

    run_a = run_repository.get(
        association_a.run_id,
    )

    assert run_a is not None

    state_b = create_state(
        selection=MODEL_B,
    )

    revision_b = WorkflowProductionRevision(
        id=REVISION_B_ID,
        state=state_b,
    )

    revision_repository.save(
        revision_b,
    )

    state_repository.set(
        state_b,
    )

    persisted_state_b = state_repository.get(
        WORKFLOW_ID,
    )

    assert persisted_state_b is not None
    assert persisted_state_b == state_b
    assert persisted_state_b != state_a

    runtime_b = create_runtime(
        state=persisted_state_b,
    )

    result_b = invoke(
        runtime=runtime_b,
        invocation_repository=invocation_repository,
        run_repository=run_repository,
        invocation_run_repository=invocation_run_repository,
    )

    invocations = invocation_repository.invocations()

    assert len(invocations) == 2

    invocation_b = invocations[1]

    association_b = invocation_run_repository.get(
        invocation_b.id,
    )

    assert association_b is not None

    run_b = run_repository.get(
        association_b.run_id,
    )

    assert run_b is not None

    assert invocation_a.workflow_id == WORKFLOW_ID
    assert invocation_b.workflow_id == WORKFLOW_ID

    assert run_a.workflow.id == WORKFLOW_ID
    assert run_b.workflow.id == WORKFLOW_ID

    assert run_a.steps[0].execution is not None
    assert run_b.steps[0].execution is not None

    assert run_a.steps[0].execution.output == "state-a"
    assert run_b.steps[0].execution.output == "state-b"

    assert (
        invocation_repository.result(
            invocation_a.id,
        )
        == result_a
    )

    assert (
        invocation_repository.result(
            invocation_b.id,
        )
        == result_b
    )

    assert (
        run_repository.get(
            run_a.id,
        )
        == run_a
    )

    assert (
        invocation_run_repository.get(
            invocation_a.id,
        )
        == association_a
    )

    assert (
        revision_repository.get(
            REVISION_A_ID,
        )
        == revision_a
    )

    assert (
        revision_repository.get(
            REVISION_B_ID,
        )
        == revision_b
    )

    assert revision_repository.revisions_for_workflow(
        WORKFLOW_ID,
    ) == (
        revision_a,
        revision_b,
    )


def test_existing_runtime_keeps_original_production_snapshot_after_state_replacement(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    state_repository = SQLiteWorkflowProductionStateRepository(
        database,
    )

    state_a = create_state(
        selection=MODEL_A,
    )

    state_b = create_state(
        selection=MODEL_B,
    )

    state_repository.set(
        state_a,
    )

    persisted_state_a = state_repository.get(
        WORKFLOW_ID,
    )

    assert persisted_state_a is not None

    runtime_a = create_runtime(
        state=persisted_state_a,
    )

    state_repository.set(
        state_b,
    )

    persisted_state_b = state_repository.get(
        WORKFLOW_ID,
    )

    assert persisted_state_b is not None

    runtime_b = create_runtime(
        state=persisted_state_b,
    )

    assert (
        runtime_a.production_state(
            WORKFLOW_ID,
        )
        == state_a
    )

    assert (
        runtime_b.production_state(
            WORKFLOW_ID,
        )
        == state_b
    )

"""End-to-end tests for durable production workflow execution."""

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
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRunRepository,
    WorkflowMetadata,
    WorkflowProductionEmission,
    WorkflowProductionModelSubstitution,
    WorkflowProductionRevision,
    WorkflowProductionState,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
    complete_production_invocation,
    create_production_invocation,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

REVISION_ID = UUID("44444444-4444-4444-4444-444444444444")

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="primary",
)

SUBSTITUTE = FixedModelSelection(
    provider="test-provider",
    model="substitute",
)


def create_model_metadata(
    selection: FixedModelSelection,
) -> ModelMetadata:
    """Create current metadata for one deterministic model."""

    return ModelMetadata(
        provider=selection.provider,
        model=selection.model,
        display_name=selection.identifier,
    )


def create_revision() -> WorkflowProductionRevision:
    """Create deterministic persisted production revision."""

    return WorkflowProductionRevision(
        id=REVISION_ID,
        state=WorkflowProductionState(
            specification=WorkflowSpecification(
                metadata=WorkflowMetadata(
                    id=WORKFLOW_ID,
                    name="production-execution-end-to-end",
                    description=("Prove durable production execution across reconstruction."),
                    version="1.0.0",
                ),
                steps=(
                    WorkflowStepSpecification(
                        id=STEP_ID,
                        specification=PromptStrategySpec(
                            metadata=StrategyMetadata(
                                id=STRATEGY_ID,
                                name="production-classifier",
                                description=("Classify the production request."),
                                version="1.0.0",
                            ),
                            prompt=Prompt(
                                text="Classify the production request.",
                            ),
                            model_selection=PRIMARY,
                        ),
                        outputs=(
                            WorkflowValueBinding(
                                name="classification",
                            ),
                        ),
                    ),
                ),
            ),
            model_substitutions=(
                WorkflowProductionModelSubstitution(
                    step_id=STEP_ID,
                    substitutes=(SUBSTITUTE,),
                ),
            ),
            emissions=(
                WorkflowProductionEmission(
                    name="label",
                    source=WorkflowValueReference(
                        producer_step_id=STEP_ID,
                        name="classification",
                    ),
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Expose only the approved substitute as currently available."""

    return ModelCatalog(
        models=(
            create_model_metadata(
                SUBSTITUTE,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Expose only the approved substitute as executable."""

    return LanguageModelRegistry(
        {
            SUBSTITUTE.identifier: DeterministicLanguageModel(
                provider=SUBSTITUTE.provider,
                model=SUBSTITUTE.model,
                response_text="positive",
            ),
        }
    )


def test_production_execution_survives_persistence_and_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    revision_repository = SQLiteWorkflowProductionRevisionRepository(
        database,
    )

    production_state_repository = SQLiteWorkflowProductionStateRepository(
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

    revision = create_revision()

    revision_repository.save(
        revision,
    )

    production_state_repository.set(
        revision.state,
    )

    invocation = create_production_invocation(
        revision=revision,
        payload={
            "text": "This came from production.",
            "private": "do not expose me",
        },
        caller_metadata={
            "request_id": "external-request-123",
            "tenant_id": "tenant-456",
        },
    )

    invocation_repository.save(
        invocation,
    )

    persisted_revision = revision_repository.get(
        revision.id,
    )

    assert persisted_revision is not None

    result = asyncio.run(
        complete_production_invocation(
            invocation=invocation,
            revision=persisted_revision,
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(),
            run_repository=run_repository,
            invocation_repository=invocation_repository,
            invocation_run_repository=invocation_run_repository,
        )
    )

    assert isinstance(
        result,
        ProductionInvocationSuccess,
    )

    reconstructed_revision_repository = SQLiteWorkflowProductionRevisionRepository(
        database,
    )

    reconstructed_state_repository = SQLiteWorkflowProductionStateRepository(
        database,
    )

    reconstructed_invocation_repository = SQLiteProductionInvocationRepository(
        database,
    )

    reconstructed_run_repository = SQLiteWorkflowRunRepository(
        database,
    )

    reconstructed_invocation_run_repository = SQLiteProductionInvocationRunRepository(
        database,
    )

    reconstructed_revision = reconstructed_revision_repository.get(
        REVISION_ID,
    )

    reconstructed_state = reconstructed_state_repository.get(
        WORKFLOW_ID,
    )

    reconstructed_invocation = reconstructed_invocation_repository.get(
        invocation.id,
    )

    reconstructed_result = reconstructed_invocation_repository.result(
        invocation.id,
    )

    reconstructed_association = reconstructed_invocation_run_repository.get(
        invocation.id,
    )

    assert reconstructed_revision == revision
    assert reconstructed_state == revision.state
    assert reconstructed_invocation == invocation
    assert reconstructed_result == result

    assert reconstructed_association is not None

    reconstructed_run = reconstructed_run_repository.get(
        reconstructed_association.run_id,
    )

    assert reconstructed_run is not None

    assert reconstructed_run.workflow.id == WORKFLOW_ID
    assert reconstructed_run.initial_context == (invocation.initial_context)

    assert reconstructed_association.invocation_id == (invocation.id)

    assert reconstructed_result.invocation_id == (invocation.id)

    assert reconstructed_result.result == {
        "label": "positive",
    }

    assert "private" not in reconstructed_result.result

    assert reconstructed_invocation.caller_metadata == {
        "request_id": "external-request-123",
        "tenant_id": "tenant-456",
    }

    reconstructed_prompt = reconstructed_revision.state.specification.steps[0].specification

    assert isinstance(
        reconstructed_prompt,
        PromptStrategySpec,
    )

    assert reconstructed_prompt.model_selection == PRIMARY

    assert reconstructed_revision.state.model_substitutions[0].substitutes == (SUBSTITUTE,)


def test_failed_production_invocation_persists_terminal_failure(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

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

    revision = create_revision()

    revision_repository.save(
        revision,
    )

    invocation = create_production_invocation(
        revision=revision,
        payload={
            "text": "Nothing executable is available.",
        },
    )

    invocation_repository.save(
        invocation,
    )

    result = asyncio.run(
        complete_production_invocation(
            invocation=invocation,
            revision=revision,
            catalog=ModelCatalog(),
            registry=LanguageModelRegistry(),
            runner=WorkflowRunner(),
            run_repository=run_repository,
            invocation_repository=invocation_repository,
            invocation_run_repository=invocation_run_repository,
        )
    )

    assert isinstance(
        result,
        ProductionInvocationFailure,
    )

    reconstructed_invocation_repository = SQLiteProductionInvocationRepository(
        database,
    )

    reconstructed_run_repository = SQLiteWorkflowRunRepository(
        database,
    )

    reconstructed_invocation_run_repository = SQLiteProductionInvocationRunRepository(
        database,
    )

    persisted_result = reconstructed_invocation_repository.result(
        invocation.id,
    )

    assert persisted_result == result

    assert isinstance(
        persisted_result,
        ProductionInvocationFailure,
    )

    assert persisted_result.error_code is (
        ProductionInvocationErrorCode.NO_APPROVED_MODEL_SUBSTITUTE
    )

    assert (
        reconstructed_invocation_run_repository.get(
            invocation.id,
        )
        is None
    )

    assert reconstructed_run_repository.runs() == ()

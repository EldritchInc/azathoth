"""Tests for configured workflow promotion application services."""

from uuid import UUID

import pytest

from azathoth.cli import promote_configured_workflow
from azathoth.prompting import (
    FixedModelSelection,
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelRequirements,
    Prompt,
)
from azathoth.runtime import (
    AzathothRuntime,
    WorkflowNotConfiguredError,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowProductionModelSubstitution,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNKNOWN_WORKFLOW_ID = UUID("99999999-9999-9999-9999-999999999999")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

PRIMARY = FixedModelSelection(
    provider="test-provider",
    model="primary",
)

SUBSTITUTE = FixedModelSelection(
    provider="test-provider",
    model="substitute",
)


def create_workflow() -> WorkflowSpecification:
    """Create one configurable workflow eligible for promotion."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="configured-promotion",
            description="Exercise configured workflow promotion.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="promotion-prompt",
                        description="Exercise configured workflow promotion.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return the deterministic production response.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )


def create_runtime() -> AzathothRuntime:
    """Create one deterministic runtime eligible for promotion."""

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
        workflows=WorkflowCatalog(
            specifications=(create_workflow(),),
        ),
        models=models,
        portfolio=ModelPortfolio(
            entries=(
                ModelPortfolioEntry(
                    provider=PRIMARY.provider,
                    model=PRIMARY.model,
                ),
            )
        ),
        language_models=LanguageModelRegistry(
            {
                PRIMARY.identifier: DeterministicLanguageModel(
                    provider=PRIMARY.provider,
                    model=PRIMARY.model,
                    response_text="success",
                ),
            }
        ),
    )


def test_promote_configured_workflow_persists_active_state_and_revision() -> None:
    runtime = create_runtime()

    production_repository = InMemoryWorkflowProductionStateRepository()

    revision_repository = InMemoryWorkflowProductionRevisionRepository()

    revision = promote_configured_workflow(
        runtime=runtime,
        workflow_id=WORKFLOW_ID,
        production_repository=production_repository,
        revision_repository=revision_repository,
    )

    state = production_repository.get(
        WORKFLOW_ID,
    )

    assert state is not None

    assert revision.state == state

    assert (
        revision_repository.get(
            revision.id,
        )
        == revision
    )

    assert revision_repository.revisions_for_workflow(
        WORKFLOW_ID,
    ) == (revision,)


def test_promote_configured_workflow_materializes_fixed_model_selection() -> None:
    production_repository = InMemoryWorkflowProductionStateRepository()

    revision = promote_configured_workflow(
        runtime=create_runtime(),
        workflow_id=WORKFLOW_ID,
        production_repository=production_repository,
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    promoted_step = revision.state.specification.steps[0].specification

    assert isinstance(
        promoted_step,
        PromptStrategySpec,
    )

    assert isinstance(
        promoted_step.model_selection,
        FixedModelSelection,
    )

    assert promoted_step.model_selection == PRIMARY


def test_promote_configured_workflow_preserves_configured_workflow() -> None:
    runtime = create_runtime()

    configured = runtime.workflows.get(
        WORKFLOW_ID,
    )

    assert configured is not None

    revision = promote_configured_workflow(
        runtime=runtime,
        workflow_id=WORKFLOW_ID,
        production_repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    assert (
        runtime.workflows.get(
            WORKFLOW_ID,
        )
        == configured
    )

    configured_prompt = configured.steps[0].specification

    assert isinstance(
        configured_prompt,
        PromptStrategySpec,
    )

    assert isinstance(
        configured_prompt.model_selection,
        PortfolioModelSelection,
    )

    promoted_prompt = revision.state.specification.steps[0].specification

    assert isinstance(
        promoted_prompt,
        PromptStrategySpec,
    )

    assert isinstance(
        promoted_prompt.model_selection,
        FixedModelSelection,
    )


def test_promote_configured_workflow_preserves_model_substitutions() -> None:
    substitution = WorkflowProductionModelSubstitution(
        step_id=STEP_ID,
        substitutes=(SUBSTITUTE,),
    )

    production_repository = InMemoryWorkflowProductionStateRepository()

    revision = promote_configured_workflow(
        runtime=create_runtime(),
        workflow_id=WORKFLOW_ID,
        production_repository=production_repository,
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
        model_substitutions=(substitution,),
    )

    assert revision.state.model_substitutions == (substitution,)

    assert (
        production_repository.get(
            WORKFLOW_ID,
        )
        == revision.state
    )


def test_promote_configured_workflow_reports_unknown_workflow() -> None:
    with pytest.raises(
        WorkflowNotConfiguredError,
        match=f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured",
    ):
        promote_configured_workflow(
            runtime=create_runtime(),
            workflow_id=UNKNOWN_WORKFLOW_ID,
            production_repository=InMemoryWorkflowProductionStateRepository(),
            revision_repository=InMemoryWorkflowProductionRevisionRepository(),
        )


def test_promote_configured_workflow_does_not_persist_unknown_workflow() -> None:
    production_repository = InMemoryWorkflowProductionStateRepository()

    revision_repository = InMemoryWorkflowProductionRevisionRepository()

    with pytest.raises(WorkflowNotConfiguredError):
        promote_configured_workflow(
            runtime=create_runtime(),
            workflow_id=UNKNOWN_WORKFLOW_ID,
            production_repository=production_repository,
            revision_repository=revision_repository,
        )

    assert production_repository.states() == ()
    assert revision_repository.revisions() == ()

"""End-to-end reconstruction of explicitly promoted workflow production state."""

from pathlib import Path
from uuid import UUID

from azathoth.cli import (
    CliRuntimeConfiguration,
    load_runtime,
)
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
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    WorkflowMetadata,
    WorkflowProductionModelSubstitution,
    WorkflowSpecification,
    WorkflowStepSpecification,
    promote_workflow_candidate,
)
from tests.model_authorization import generate_workflow_candidate

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

PRIMARY_IDENTIFIER = "test-provider/promoted-model"

FIRST_SUBSTITUTE_IDENTIFIER = "fallback-provider/first-fallback"

SECOND_SUBSTITUTE_IDENTIFIER = "fallback-provider/second-fallback"


def create_configured_workflow() -> WorkflowSpecification:
    """Create a portfolio-selected durable configured workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="promotion-reconstruction",
            description=("Prove explicit promotion survives durable reconstruction."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="promotion-prompt",
                        description=("Exercise end-to-end promotion reconstruction."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )


def create_model_catalog() -> ModelCatalog:
    """Create the model selected by the executable candidate."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test-provider",
                model="promoted-model",
                display_name="Promoted Model",
                context_window_tokens=8_192,
            ),
        )
    )


def create_model_registry() -> LanguageModelRegistry:
    """Create an executable implementation for the selected model."""

    return LanguageModelRegistry(
        models={
            PRIMARY_IDENTIFIER: DeterministicLanguageModel(
                provider="test-provider",
                model="promoted-model",
                response_text="success",
            ),
        }
    )


def create_substitutions() -> tuple[WorkflowProductionModelSubstitution, ...]:
    """Create explicitly approved ordered production substitutes."""

    return (
        WorkflowProductionModelSubstitution(
            step_id=STEP_ID,
            substitutes=(
                FixedModelSelection(
                    provider="fallback-provider",
                    model="first-fallback",
                ),
                FixedModelSelection(
                    provider="fallback-provider",
                    model="second-fallback",
                ),
            ),
        ),
    )


def require_prompt(
    specification: WorkflowSpecification,
) -> PromptStrategySpec:
    """Return the deterministic prompt specification."""

    prompt = specification.steps[0].specification

    assert isinstance(
        prompt,
        PromptStrategySpec,
    )

    return prompt


def test_promoted_workflow_survives_runtime_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    configured = create_configured_workflow()

    SQLiteWorkflowRepository(
        database,
    ).save(
        configured,
    )

    runtime_before_promotion = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    assert (
        runtime_before_promotion.production_state(
            WORKFLOW_ID,
        )
        is None
    )

    candidate = generate_workflow_candidate(
        specification=configured,
        catalog=create_model_catalog(),
        registry=create_model_registry(),
    )

    production_repository = SQLiteWorkflowProductionStateRepository(
        database,
    )

    promoted = promote_workflow_candidate(
        specification=configured,
        candidate=candidate,
        repository=production_repository,
        model_substitutions=create_substitutions(),
    )

    assert (
        production_repository.get(
            WORKFLOW_ID,
        )
        == promoted
    )

    reconstructed = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    reconstructed_configured = reconstructed.workflows.get(
        WORKFLOW_ID,
    )

    reconstructed_production = reconstructed.production_state(
        WORKFLOW_ID,
    )

    assert reconstructed_configured == configured
    assert reconstructed_production == promoted

    assert reconstructed_production is not None

    configured_prompt = require_prompt(
        reconstructed_configured,
    )

    production_prompt = require_prompt(
        reconstructed_production.specification,
    )

    assert isinstance(
        configured_prompt.model_selection,
        PortfolioModelSelection,
    )

    assert isinstance(
        production_prompt.model_selection,
        FixedModelSelection,
    )

    assert production_prompt.model_selection.identifier == (PRIMARY_IDENTIFIER)

    assert tuple(
        substitution.step_id for substitution in reconstructed_production.model_substitutions
    ) == (STEP_ID,)

    assert tuple(
        model.identifier for model in reconstructed_production.model_substitutions[0].substitutes
    ) == (
        FIRST_SUBSTITUTE_IDENTIFIER,
        SECOND_SUBSTITUTE_IDENTIFIER,
    )

    assert (
        runtime_before_promotion.production_state(
            WORKFLOW_ID,
        )
        is None
    )


def test_repromotion_replaces_only_production_state_after_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    configured = create_configured_workflow()

    SQLiteWorkflowRepository(
        database,
    ).save(
        configured,
    )

    candidate = generate_workflow_candidate(
        specification=configured,
        catalog=create_model_catalog(),
        registry=create_model_registry(),
    )

    repository = SQLiteWorkflowProductionStateRepository(
        database,
    )

    first = promote_workflow_candidate(
        specification=configured,
        candidate=candidate,
        repository=repository,
    )

    first_runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    second = promote_workflow_candidate(
        specification=configured,
        candidate=candidate,
        repository=repository,
        model_substitutions=create_substitutions(),
    )

    second_runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    first_production = first_runtime.production_state(
        WORKFLOW_ID,
    )

    second_production = second_runtime.production_state(
        WORKFLOW_ID,
    )

    assert first_production == first
    assert second_production == second

    assert first != second

    assert (
        first_runtime.workflows.get(
            WORKFLOW_ID,
        )
        == configured
    )

    assert (
        second_runtime.workflows.get(
            WORKFLOW_ID,
        )
        == configured
    )

    assert first_production is not None
    assert second_production is not None

    assert first_production.model_substitutions == ()

    assert second_production.model_substitutions == (create_substitutions())

    assert (
        first_runtime.production_state(
            WORKFLOW_ID,
        )
        == first
    )

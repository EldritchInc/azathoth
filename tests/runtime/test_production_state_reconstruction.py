"""End-to-end tests for reconstructed workflow production state."""

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
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

PRODUCTION_MODEL = "production-model"

REPLACEMENT_MODEL = "replacement-model"


def create_configured_workflow() -> WorkflowSpecification:
    """Create the durable configured workflow definition."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="production-state-reconstruction",
            description=("Prove configured and production workflow state remain distinct."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="configured-prompt",
                        description="Exercise reconstructed production state.",
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


def create_production_workflow(
    *,
    model: str,
) -> WorkflowSpecification:
    """Create a production specialization of the configured workflow."""

    configured = create_configured_workflow()

    prompt = configured.steps[0].specification

    assert isinstance(
        prompt,
        PromptStrategySpec,
    )

    production_prompt = prompt.model_copy(
        update={
            "model_selection": FixedModelSelection(
                provider="test-provider",
                model=model,
            ),
        }
    )

    production_step = configured.steps[0].model_copy(
        update={
            "specification": production_prompt,
        }
    )

    return configured.model_copy(
        update={
            "steps": (production_step,),
        }
    )


def require_prompt(
    specification: WorkflowSpecification,
) -> PromptStrategySpec:
    """Return the prompt specification from the deterministic workflow."""

    prompt = specification.steps[0].specification

    assert isinstance(
        prompt,
        PromptStrategySpec,
    )

    return prompt


def test_reconstructed_runtime_keeps_configured_and_production_state_distinct(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    configured = create_configured_workflow()

    production = WorkflowProductionState(
        specification=create_production_workflow(
            model=PRODUCTION_MODEL,
        )
    )

    SQLiteWorkflowRepository(
        database,
    ).save(
        configured,
    )

    SQLiteWorkflowProductionStateRepository(
        database,
    ).set(
        production,
    )

    runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    reconstructed_configured = runtime.workflows.get(
        WORKFLOW_ID,
    )

    reconstructed_production = runtime.production_state(
        WORKFLOW_ID,
    )

    assert reconstructed_configured == configured
    assert reconstructed_production == production

    assert reconstructed_production is not None

    assert reconstructed_configured != reconstructed_production.specification

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

    assert production_prompt.model_selection.identifier == (f"test-provider/{PRODUCTION_MODEL}")


def test_reconstructed_runtime_observes_replaced_production_state_without_mutating_configuration(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    configured = create_configured_workflow()

    production_repository = SQLiteWorkflowProductionStateRepository(
        database,
    )

    SQLiteWorkflowRepository(
        database,
    ).save(
        configured,
    )

    production_repository.set(
        WorkflowProductionState(
            specification=create_production_workflow(
                model=PRODUCTION_MODEL,
            )
        )
    )

    first_runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    first_production = first_runtime.production_state(
        WORKFLOW_ID,
    )

    assert first_production is not None

    first_prompt = require_prompt(
        first_production.specification,
    )

    assert isinstance(
        first_prompt.model_selection,
        FixedModelSelection,
    )

    assert first_prompt.model_selection.identifier == (f"test-provider/{PRODUCTION_MODEL}")

    production_repository.set(
        WorkflowProductionState(
            specification=create_production_workflow(
                model=REPLACEMENT_MODEL,
            )
        )
    )

    second_runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    reconstructed_configured = second_runtime.workflows.get(
        WORKFLOW_ID,
    )

    second_production = second_runtime.production_state(
        WORKFLOW_ID,
    )

    assert reconstructed_configured == configured
    assert second_production is not None

    configured_prompt = require_prompt(
        reconstructed_configured,
    )

    second_prompt = require_prompt(
        second_production.specification,
    )

    assert isinstance(
        configured_prompt.model_selection,
        PortfolioModelSelection,
    )

    assert isinstance(
        second_prompt.model_selection,
        FixedModelSelection,
    )

    assert second_prompt.model_selection.identifier == (f"test-provider/{REPLACEMENT_MODEL}")

    assert (
        first_runtime.production_state(
            WORKFLOW_ID,
        )
        == first_production
    )

    assert (
        first_runtime.production_state(
            WORKFLOW_ID,
        )
        != second_production
    )

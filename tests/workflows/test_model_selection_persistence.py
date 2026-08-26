"""Tests for durable workflow model-selection authority."""

from pathlib import Path
from uuid import UUID

from azathoth.prompting import (
    FixedModelSelection,
    ModelSelection,
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelCapability,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    decode_workflow_document,
    encode_workflow_document,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_workflow(
    model_selection: ModelSelection,
) -> WorkflowSpecification:
    """Create one deterministic workflow with model-selection authority."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Model selection workflow",
            description="Exercise durable model-selection authority.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Model selection prompt",
                        description="Exercise one model-selection policy.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=model_selection,
                ),
            ),
        ),
    )


def require_prompt_specification(
    workflow: WorkflowSpecification,
) -> PromptStrategySpec:
    """Return the prompt specification from the deterministic test workflow."""

    specification = workflow.steps[0].specification

    assert isinstance(
        specification,
        PromptStrategySpec,
    )

    return specification


def test_workflow_document_preserves_portfolio_model_selection() -> None:
    workflow = create_workflow(
        PortfolioModelSelection(
            requirements=ModelRequirements(
                required_capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                minimum_context_window_tokens=128_000,
            )
        )
    )

    reconstructed = decode_workflow_document(encode_workflow_document(workflow))

    selection = require_prompt_specification(reconstructed).model_selection

    assert isinstance(
        selection,
        PortfolioModelSelection,
    )
    assert selection.requirements == ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        minimum_context_window_tokens=128_000,
    )
    assert reconstructed == workflow


def test_workflow_document_preserves_fixed_model_selection() -> None:
    workflow = create_workflow(
        FixedModelSelection(
            provider="example-provider",
            model="example-model",
        )
    )

    reconstructed = decode_workflow_document(encode_workflow_document(workflow))

    selection = require_prompt_specification(reconstructed).model_selection

    assert isinstance(
        selection,
        FixedModelSelection,
    )
    assert selection.provider == "example-provider"
    assert selection.model == "example-model"
    assert selection.identifier == ("example-provider/example-model")
    assert reconstructed == workflow


def test_sqlite_repository_preserves_portfolio_model_selection_after_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "workflows.db"

    workflow = create_workflow(
        PortfolioModelSelection(
            requirements=ModelRequirements(
                required_capabilities=frozenset(
                    {
                        ModelCapability.TOOL_USE,
                    }
                ),
                minimum_context_window_tokens=64_000,
            )
        )
    )

    repository = SQLiteWorkflowRepository(database)

    repository.save(workflow)

    reconstructed_repository = SQLiteWorkflowRepository(database)

    reconstructed = reconstructed_repository.get(WORKFLOW_ID)

    assert reconstructed is not None

    selection = require_prompt_specification(reconstructed).model_selection

    assert isinstance(
        selection,
        PortfolioModelSelection,
    )
    assert selection.requirements == ModelRequirements(
        required_capabilities=frozenset(
            {
                ModelCapability.TOOL_USE,
            }
        ),
        minimum_context_window_tokens=64_000,
    )
    assert reconstructed == workflow


def test_sqlite_repository_preserves_fixed_model_selection_after_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "workflows.db"

    workflow = create_workflow(
        FixedModelSelection(
            provider="example-provider",
            model="fixed-model",
        )
    )

    repository = SQLiteWorkflowRepository(database)

    repository.save(workflow)

    reconstructed_repository = SQLiteWorkflowRepository(database)

    reconstructed = reconstructed_repository.get(WORKFLOW_ID)

    assert reconstructed is not None

    selection = require_prompt_specification(reconstructed).model_selection

    assert isinstance(
        selection,
        FixedModelSelection,
    )
    assert selection.provider == "example-provider"
    assert selection.model == "fixed-model"
    assert selection.identifier == ("example-provider/fixed-model")
    assert reconstructed == workflow

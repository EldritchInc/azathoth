"""Workflow tests for fixed model-selection authority."""

from uuid import UUID

import pytest

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
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowGenerationError,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def create_workflow() -> WorkflowSpecification:
    """Create a workflow requiring one exact unavailable model."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Fixed model workflow",
            description="Require one exact model.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Fixed model prompt",
                        description="Require one exact model.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=FixedModelSelection(
                        provider="example",
                        model="required",
                    ),
                ),
            ),
        ),
    )


def test_fixed_model_selection_does_not_fall_back_to_available_model() -> None:
    available = ModelMetadata(
        provider="example",
        model="available",
        display_name="Available model",
        context_window_tokens=128_000,
    )

    catalog = ModelCatalog(models=(available,))

    registry = LanguageModelRegistry(
        models={
            available.identifier: DeterministicLanguageModel(
                provider=available.provider,
                model=available.model,
            ),
        }
    )

    with pytest.raises(
        WorkflowGenerationError,
        match="No executable prompt candidate could be generated",
    ):
        generate_workflow_candidate(
            specification=create_workflow(),
            catalog=catalog,
            registry=registry,
            portfolio=ModelPortfolio(),
        )

"""Tests for generating context-aware prompt workflow candidates."""

from uuid import UUID

import pytest

from azathoth.prompting import (
    ContextPromptStrategy,
    ContextPromptStrategySpec,
    FixedModelSelection,
    PortfolioModelSelection,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowGenerationError,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

MODEL_IDENTIFIER = "deterministic/context-classifier"


def create_template() -> PromptTemplate:
    """Create one deterministic context-aware prompt template."""

    return PromptTemplate(
        text=("Classify this request as positive or negative.\n\nRequest: {request}"),
        bindings=(
            PromptBinding(
                variable_name="request",
                event_type="request.received",
                field_name="input",
            ),
        ),
    )


def create_workflow(
    *,
    fixed: bool = False,
) -> WorkflowSpecification:
    """Create one durable context-aware workflow."""

    model_selection = (
        FixedModelSelection(
            provider="deterministic",
            model="context-classifier",
        )
        if fixed
        else PortfolioModelSelection(
            requirements=ModelRequirements(),
        )
    )

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Context-aware classification",
            description="Classify externally supplied request text.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=ContextPromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Classify request",
                        description=("Classify one request rendered from execution context."),
                        version="1.0.0",
                    ),
                    template=create_template(),
                    model_selection=model_selection,
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                    ),
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create deterministic model metadata."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="deterministic",
                model="context-classifier",
                display_name="Deterministic Context Classifier",
                context_window_tokens=8_192,
            ),
        ),
    )


def create_registry() -> LanguageModelRegistry:
    """Create one executable deterministic language model."""

    return LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider="deterministic",
                model="context-classifier",
                response_text="positive",
            ),
        }
    )


def test_generation_produces_context_prompt_strategy() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    assert len(candidate.steps) == 1

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        ContextPromptStrategy,
    )


def test_generation_preserves_context_prompt_template() -> None:
    workflow = create_workflow()

    specification = workflow.steps[0].specification

    assert isinstance(
        specification,
        ContextPromptStrategySpec,
    )

    candidate = generate_workflow_candidate(
        specification=workflow,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        ContextPromptStrategy,
    )

    assert strategy.template == specification.template


def test_generation_preserves_context_prompt_model_binding() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        ContextPromptStrategy,
    )

    binding = strategy.model_binding

    assert binding is not None
    assert binding.identifier == MODEL_IDENTIFIER


def test_generation_preserves_context_prompt_model_requirements() -> None:
    workflow = create_workflow()

    specification = workflow.steps[0].specification

    assert isinstance(
        specification,
        ContextPromptStrategySpec,
    )

    selection = specification.model_selection

    assert isinstance(
        selection,
        PortfolioModelSelection,
    )

    candidate = generate_workflow_candidate(
        specification=workflow,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        ContextPromptStrategy,
    )

    assert strategy.model_requirements == (selection.requirements)


def test_generation_preserves_context_prompt_step_topology() -> None:
    workflow = create_workflow()

    candidate = generate_workflow_candidate(
        specification=workflow,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    generated_step = candidate.steps[0]
    configured_step = workflow.steps[0]

    assert generated_step.id == configured_step.id
    assert generated_step.depends_on == configured_step.depends_on
    assert generated_step.inputs == configured_step.inputs
    assert generated_step.outputs == configured_step.outputs
    assert generated_step.conditions == configured_step.conditions
    assert generated_step.retry_policy == configured_step.retry_policy
    assert generated_step.failure_policy == configured_step.failure_policy


def test_context_prompt_generation_is_deterministic() -> None:
    workflow = create_workflow()
    catalog = create_catalog()
    registry = create_registry()

    first = generate_workflow_candidate(
        specification=workflow,
        catalog=catalog,
        registry=registry,
    )

    second = generate_workflow_candidate(
        specification=workflow,
        catalog=catalog,
        registry=registry,
    )

    first_strategy = first.steps[0].strategy
    second_strategy = second.steps[0].strategy

    assert isinstance(
        first_strategy,
        ContextPromptStrategy,
    )

    assert isinstance(
        second_strategy,
        ContextPromptStrategy,
    )

    assert first_strategy.metadata.id == second_strategy.metadata.id


def test_context_prompt_generation_respects_fixed_model_selection() -> None:
    candidate = generate_workflow_candidate(
        specification=create_workflow(
            fixed=True,
        ),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        ContextPromptStrategy,
    )

    binding = strategy.model_binding

    assert binding is not None
    assert binding.identifier == MODEL_IDENTIFIER


def test_context_prompt_generation_fails_without_executable_model() -> None:
    with pytest.raises(
        WorkflowGenerationError,
        match=("No executable context prompt candidate could be generated"),
    ):
        generate_workflow_candidate(
            specification=create_workflow(),
            catalog=create_catalog(),
            registry=LanguageModelRegistry(models={}),
        )

"""Tests for workflow candidate generation through AzathothRuntime."""

from uuid import UUID

import pytest

from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategy,
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
from azathoth.runtime import (
    AzathothRuntime,
    RuntimeEnvironment,
    WorkflowNotConfiguredError,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    ToolCatalog,
    ToolDefinition,
    ToolImplementation,
    ToolImplementationCatalog,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
    ToolStrategy,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowCatalog,
    WorkflowGenerationError,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from tests.model_authorization import (
    portfolio_for_catalog,
)

PROMPT_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

PROMPT_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

PROMPT_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

TOOL_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

TOOL_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

TOOL_ID = UUID("66666666-6666-6666-6666-666666666666")

IMPLEMENTATION_ID = UUID("77777777-7777-7777-7777-777777777777")

UNKNOWN_WORKFLOW_ID = UUID("88888888-8888-8888-8888-888888888888")

MODEL_IDENTIFIER = "test/example"


def create_prompt_workflow() -> WorkflowSpecification:
    """Create one prompt-backed workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=PROMPT_WORKFLOW_ID,
            name="prompt workflow",
            description="Execute one prompt-backed step.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=PROMPT_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=PROMPT_STRATEGY_ID,
                        name="prompt step",
                        description="Return one deterministic response.",
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


def create_tool_definition() -> ToolDefinition:
    """Create one deterministic tool definition."""

    return ToolDefinition(
        id=TOOL_ID,
        name="example tool",
        description="Return structured input unchanged.",
        version="1.0.0",
        input_schema=ToolInputSchema(
            json_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            }
        ),
        output_schema=ToolOutputSchema(
            json_schema={
                "type": "object",
            }
        ),
    )


def create_tool_workflow() -> WorkflowSpecification:
    """Create one tool-backed workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=TOOL_WORKFLOW_ID,
            name="tool workflow",
            description="Execute one tool-backed step.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=TOOL_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="example tool",
                        version="1.0.0",
                    )
                ),
            ),
        ),
    )


def create_model_catalog() -> ModelCatalog:
    """Create configured model metadata."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="example",
                display_name="Example Model",
                context_window_tokens=8_192,
            ),
        )
    )


def create_language_model_registry() -> LanguageModelRegistry:
    """Create executable language-model implementations."""

    return LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model="example",
                response_text="success",
            ),
        }
    )


def create_runtime(
    *,
    include_tools: bool = True,
) -> AzathothRuntime:
    """Create runtime configuration for candidate generation."""

    workflows = WorkflowCatalog(
        specifications=(
            create_prompt_workflow(),
            create_tool_workflow(),
        )
    )

    models = create_model_catalog()

    portfolio = portfolio_for_catalog(models)

    if not include_tools:
        return AzathothRuntime(
            workflows=workflows,
            models=models,
            portfolio=portfolio,
            language_models=create_language_model_registry(),
        )

    return AzathothRuntime(
        workflows=workflows,
        models=models,
        portfolio=portfolio,
        language_models=create_language_model_registry(),
        tools=ToolCatalog(definitions=(create_tool_definition(),)),
        tool_implementations=ToolImplementationCatalog(
            implementations=(
                ToolImplementation(
                    id=IMPLEMENTATION_ID,
                    tool_id=TOOL_ID,
                    tool_version="1.0.0",
                    version="1.0.0",
                    runtime="python",
                    source=("def run(inputs):\n    return inputs\n"),
                ),
            )
        ),
    )


def test_runtime_generates_prompt_workflow_candidate() -> None:
    runtime = create_runtime()

    candidate = runtime.generate_workflow_candidate(PROMPT_WORKFLOW_ID)

    assert candidate.metadata.id == PROMPT_WORKFLOW_ID
    assert len(candidate.steps) == 1

    step = candidate.steps[0]

    assert step.id == PROMPT_STEP_ID

    strategy = step.strategy

    assert isinstance(
        strategy,
        PromptStrategy,
    )

    assert strategy.model_binding is not None
    assert strategy.model_binding.identifier == MODEL_IDENTIFIER


def test_runtime_generates_tool_workflow_candidate() -> None:
    runtime = create_runtime()

    candidate = runtime.generate_workflow_candidate(TOOL_WORKFLOW_ID)

    assert candidate.metadata.id == TOOL_WORKFLOW_ID
    assert len(candidate.steps) == 1

    step = candidate.steps[0]

    assert step.id == TOOL_STEP_ID

    assert isinstance(
        step.strategy,
        ToolStrategy,
    )


def test_runtime_generation_preserves_workflow_metadata() -> None:
    runtime = create_runtime()

    candidate = runtime.generate_workflow_candidate(PROMPT_WORKFLOW_ID)

    specification = runtime.workflows.get(PROMPT_WORKFLOW_ID)

    assert specification is not None
    assert candidate.metadata == specification.metadata


def test_runtime_raises_for_unknown_workflow() -> None:
    runtime = create_runtime()

    with pytest.raises(
        WorkflowNotConfiguredError,
        match=(f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured"),
    ):
        runtime.generate_workflow_candidate(UNKNOWN_WORKFLOW_ID)


def test_runtime_preserves_candidate_generation_failures() -> None:
    runtime = create_runtime(include_tools=False)

    with pytest.raises(
        WorkflowGenerationError,
        match="No tool definition satisfies requirement",
    ):
        runtime.generate_workflow_candidate(TOOL_WORKFLOW_ID)


def test_runtime_environment_exposes_candidate_generation() -> None:
    runtime: RuntimeEnvironment = create_runtime()

    candidate = runtime.generate_workflow_candidate(PROMPT_WORKFLOW_ID)

    assert candidate.metadata.id == PROMPT_WORKFLOW_ID

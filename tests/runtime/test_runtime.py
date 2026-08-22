"""Tests for process-local Azathoth runtime composition."""

from uuid import UUID

from azathoth.prompting import PromptStrategySpec
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
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    ToolCatalog,
    ToolDefinition,
    ToolImplementation,
    ToolImplementationCatalog,
    ToolInputSchema,
    ToolOutputSchema,
)
from azathoth.workflows import (
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

TOOL_ID = UUID("44444444-4444-4444-4444-444444444444")

IMPLEMENTATION_ID = UUID("55555555-5555-5555-5555-555555555555")

MODEL_IDENTIFIER = "test/example"


def create_workflow_catalog() -> WorkflowCatalog:
    """Create one deterministic workflow catalog."""

    workflow = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="runtime workflow",
            description="Exercise runtime composition.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="runtime prompt",
                        description="Exercise runtime model composition.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_requirements=ModelRequirements(),
                ),
            ),
        ),
    )

    return WorkflowCatalog(specifications=(workflow,))


def create_model_catalog() -> ModelCatalog:
    """Create one deterministic model catalog."""

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
    """Create one executable language-model registry."""

    return LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model="example",
                response_text="success",
            ),
        }
    )


def create_tool_catalog() -> ToolCatalog:
    """Create one deterministic tool catalog."""

    return ToolCatalog(
        definitions=(
            ToolDefinition(
                id=TOOL_ID,
                name="example tool",
                description="Execute one deterministic example tool.",
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
            ),
        )
    )


def create_tool_implementation_catalog() -> ToolImplementationCatalog:
    """Create one deterministic tool implementation catalog."""

    return ToolImplementationCatalog(
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
    )


def test_runtime_exposes_configured_dependencies() -> None:
    workflows = create_workflow_catalog()
    models = create_model_catalog()
    language_models = create_language_model_registry()
    tools = create_tool_catalog()
    implementations = create_tool_implementation_catalog()

    runtime = AzathothRuntime(
        workflows=workflows,
        models=models,
        language_models=language_models,
        tools=tools,
        tool_implementations=implementations,
    )

    assert runtime.workflows is workflows
    assert runtime.models is models
    assert runtime.language_models is language_models
    assert runtime.tools is tools
    assert runtime.tool_implementations is implementations


def test_runtime_defaults_to_empty_tool_catalogs() -> None:
    runtime = AzathothRuntime(
        workflows=create_workflow_catalog(),
        models=create_model_catalog(),
        language_models=create_language_model_registry(),
    )

    assert runtime.tools.definitions == ()
    assert runtime.tool_implementations.implementations == ()


def test_runtime_satisfies_runtime_environment_protocol() -> None:
    runtime: RuntimeEnvironment = AzathothRuntime(
        workflows=create_workflow_catalog(),
        models=create_model_catalog(),
        language_models=create_language_model_registry(),
    )

    assert runtime.workflows.identifiers == (WORKFLOW_ID,)


def test_runtime_reuses_tool_resolver() -> None:
    runtime = AzathothRuntime(
        workflows=create_workflow_catalog(),
        models=create_model_catalog(),
        language_models=create_language_model_registry(),
        tools=create_tool_catalog(),
    )

    assert runtime.tool_resolver is runtime.tool_resolver


def test_runtime_reuses_tool_implementation_resolver() -> None:
    runtime = AzathothRuntime(
        workflows=create_workflow_catalog(),
        models=create_model_catalog(),
        language_models=create_language_model_registry(),
        tool_implementations=create_tool_implementation_catalog(),
    )

    assert runtime.tool_implementation_resolver is runtime.tool_implementation_resolver

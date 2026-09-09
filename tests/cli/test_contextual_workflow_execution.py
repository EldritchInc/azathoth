"""End-to-end tests for configured workflows consuming external context."""

import asyncio
from uuid import UUID

from azathoth.cli import execute_configured_workflow
from azathoth.context import Context, ContextEvent
from azathoth.prompting import (
    ContextPromptStrategySpec,
    PortfolioModelSelection,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    ModelResponse,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    ToolCatalog,
    ToolDefinition,
    ToolImplementation,
    ToolImplementationCatalog,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowCatalog,
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
)
from tests.model_authorization import portfolio_for_catalog

CONTEXT_PROMPT_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

CONTEXT_PROMPT_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

CONTEXT_PROMPT_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

TOOL_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

TOOL_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

TOOL_ID = UUID("66666666-6666-6666-6666-666666666666")

TOOL_IMPLEMENTATION_ID = UUID("77777777-7777-7777-7777-777777777777")

MODEL_IDENTIFIER = "test/context-model"


class RecordingLanguageModel:
    """Record the rendered prompt and return deterministic output."""

    def __init__(self) -> None:
        self.received_prompt: Prompt | None = None

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record one prompt and return a deterministic response."""

        self.received_prompt = prompt

        return ModelResponse(
            text="positive",
            provider="test",
            model="context-model",
            prompt_tokens=10,
            completion_tokens=1,
            total_tokens=11,
            latency_ms=5,
            estimated_cost_usd=0.0001,
        )


def create_context_prompt_workflow() -> WorkflowSpecification:
    """Create a configured workflow that renders caller input into a prompt."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=CONTEXT_PROMPT_WORKFLOW_ID,
            name="Context prompt execution",
            description="Render caller input into a configured prompt.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=CONTEXT_PROMPT_STEP_ID,
                specification=ContextPromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=CONTEXT_PROMPT_STRATEGY_ID,
                        name="Classify request",
                        description="Classify caller-supplied request text.",
                        version="1.0.0",
                    ),
                    template=PromptTemplate(
                        text=(
                            "Classify this request as positive or negative.\n\nRequest: {request}"
                        ),
                        bindings=(
                            PromptBinding(
                                variable_name="request",
                                event_type="request.received",
                                field_name="input",
                            ),
                        ),
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                    ),
                ),
            ),
        ),
    )


def create_context_prompt_runtime(
    language_model: RecordingLanguageModel,
) -> AzathothRuntime:
    """Create one runtime containing a context-aware prompt workflow."""

    models = ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="context-model",
                display_name="Context Test Model",
                context_window_tokens=8_192,
            ),
        ),
    )

    return AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=(create_context_prompt_workflow(),),
        ),
        models=models,
        portfolio=portfolio_for_catalog(
            models,
        ),
        language_models=LanguageModelRegistry(
            models={
                MODEL_IDENTIFIER: language_model,
            },
        ),
    )


def create_tool_workflow() -> WorkflowSpecification:
    """Create a configured first-step tool consuming caller context."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=TOOL_WORKFLOW_ID,
            name="Context tool execution",
            description="Pass caller input into a configured tool.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=TOOL_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="word_count",
                        version="1.0.0",
                        runtime="python",
                    ),
                ),
                inputs=(
                    WorkflowInputBinding(
                        name="text",
                        source=WorkflowContextReference(
                            event_type="request.received",
                            field_name="input",
                        ),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="word_count",
                        path=("word_count",),
                    ),
                ),
            ),
        ),
    )


def create_tool_catalog() -> ToolCatalog:
    """Create the configured word-count capability."""

    return ToolCatalog(
        definitions=(
            ToolDefinition(
                id=TOOL_ID,
                name="word_count",
                description="Count whitespace-delimited words.",
                version="1.0.0",
                input_schema=ToolInputSchema(
                    json_schema={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "text",
                        ],
                        "additionalProperties": False,
                    },
                ),
                output_schema=ToolOutputSchema(
                    json_schema={
                        "type": "object",
                        "properties": {
                            "word_count": {
                                "type": "integer",
                            },
                        },
                        "required": [
                            "word_count",
                        ],
                    },
                ),
            ),
        ),
    )


def create_tool_implementation_catalog() -> ToolImplementationCatalog:
    """Create one executable implementation of the word-count capability."""

    return ToolImplementationCatalog(
        implementations=(
            ToolImplementation(
                id=TOOL_IMPLEMENTATION_ID,
                tool_id=TOOL_ID,
                tool_version="1.0.0",
                version="1.0.0",
                runtime="python",
                entrypoint="run",
                source=(
                    "def run(text: str) -> dict[str, int]:\n"
                    "    return {'word_count': len(text.split())}\n"
                ),
            ),
        ),
    )


def create_tool_runtime() -> AzathothRuntime:
    """Create one runtime containing a context-fed tool workflow."""

    models = ModelCatalog()

    return AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=(create_tool_workflow(),),
        ),
        models=models,
        portfolio=portfolio_for_catalog(
            models,
        ),
        language_models=LanguageModelRegistry(),
        tools=create_tool_catalog(),
        tool_implementations=create_tool_implementation_catalog(),
    )


def create_request_context(
    value: str,
) -> Context:
    """Create one external request event."""

    return Context(
        events=(
            ContextEvent(
                event_type="request.received",
                payload={
                    "input": value,
                },
                producer="test-client",
            ),
        ),
    )


def test_configured_context_prompt_consumes_supplied_context() -> None:
    language_model = RecordingLanguageModel()

    run = asyncio.run(
        execute_configured_workflow(
            runtime=create_context_prompt_runtime(
                language_model,
            ),
            workflow_id=CONTEXT_PROMPT_WORKFLOW_ID,
            context=create_request_context(
                "I absolutely loved this.",
            ),
        )
    )

    assert run.succeeded

    assert language_model.received_prompt is not None

    assert language_model.received_prompt.text == (
        "Classify this request as positive or negative.\n\nRequest: I absolutely loved this."
    )

    execution = run.steps[0].execution

    assert execution is not None
    assert execution.output == "positive"

    values = run.values_named(
        "classification",
    )

    assert len(values) == 1
    assert values[0].value == "positive"


def test_configured_context_prompt_changes_with_caller_input() -> None:
    first_model = RecordingLanguageModel()

    asyncio.run(
        execute_configured_workflow(
            runtime=create_context_prompt_runtime(
                first_model,
            ),
            workflow_id=CONTEXT_PROMPT_WORKFLOW_ID,
            context=create_request_context(
                "First request.",
            ),
        )
    )

    second_model = RecordingLanguageModel()

    asyncio.run(
        execute_configured_workflow(
            runtime=create_context_prompt_runtime(
                second_model,
            ),
            workflow_id=CONTEXT_PROMPT_WORKFLOW_ID,
            context=create_request_context(
                "Second request.",
            ),
        )
    )

    assert first_model.received_prompt is not None
    assert second_model.received_prompt is not None

    assert first_model.received_prompt.text.endswith("Request: First request.")

    assert second_model.received_prompt.text.endswith("Request: Second request.")

    assert first_model.received_prompt.text != second_model.received_prompt.text


def test_configured_first_step_tool_consumes_supplied_context() -> None:
    run = asyncio.run(
        execute_configured_workflow(
            runtime=create_tool_runtime(),
            workflow_id=TOOL_WORKFLOW_ID,
            context=create_request_context(
                "one two three four five",
            ),
        )
    )

    assert run.succeeded

    execution = run.steps[0].execution

    assert execution is not None

    assert execution.output == {
        "word_count": 5,
    }

    values = run.values_named(
        "word_count",
    )

    assert len(values) == 1
    assert values[0].value == 5


def test_configured_first_step_tool_records_external_input_provenance() -> None:
    run = asyncio.run(
        execute_configured_workflow(
            runtime=create_tool_runtime(),
            workflow_id=TOOL_WORKFLOW_ID,
            context=create_request_context(
                "one two three",
            ),
        )
    )

    execution = run.steps[0].execution

    assert execution is not None

    bound_inputs = execution.initial_context.by_type(
        "workflow.input.bound",
    )

    assert len(bound_inputs) == 1

    assert bound_inputs[0].producer == "workflow-runner"

    assert bound_inputs[0].payload == {
        "name": "text",
        "value": "one two three",
        "source_event_type": "request.received",
        "source_field_name": "input",
    }

"""End-to-end execution through reconstructed Azathoth runtime configuration."""

import asyncio
from pathlib import Path
from uuid import UUID

from azathoth.context import Context
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalogLoader,
    ModelMetadata,
    ModelRequirements,
    Prompt,
    SQLiteModelRepository,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    SQLiteToolRepository,
    ToolCatalogLoader,
    ToolDefinition,
    ToolImplementation,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
)
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    ToolStepSpecification,
    WorkflowCatalogLoader,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

PROMPT_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

PROMPT_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

TOOL_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

TOOL_ID = UUID("55555555-5555-5555-5555-555555555555")

IMPLEMENTATION_ID = UUID("66666666-6666-6666-6666-666666666666")

MODEL_IDENTIFIER = "test/example"


def create_workflow() -> WorkflowSpecification:
    """Create one workflow using both model-backed and tool-backed steps."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="reconstructed runtime workflow",
            description=("Execute reconstructed prompt and tool configuration."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=PROMPT_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=PROMPT_STRATEGY_ID,
                        name="produce message",
                        description=("Produce one deterministic message."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="message",
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=TOOL_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="identity tool",
                        version="1.0.0",
                    )
                ),
                depends_on=(PROMPT_STEP_ID,),
                outputs=(
                    WorkflowValueBinding(
                        name="result",
                    ),
                ),
            ),
        ),
    )


def create_model() -> ModelMetadata:
    """Create durable metadata for the runtime language model."""

    return ModelMetadata(
        provider="test",
        model="example",
        display_name="Example Model",
        context_window_tokens=8_192,
    )


def create_tool_definition() -> ToolDefinition:
    """Create one durable tool capability."""

    return ToolDefinition(
        id=TOOL_ID,
        name="identity tool",
        description="Return deterministic structured output.",
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


def create_tool_implementation() -> ToolImplementation:
    """Create one durable Python tool implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        source=("def run():\n    return {'status': 'tool success'}\n"),
    )


def persist_configuration(
    *,
    workflow_database: Path,
    model_database: Path,
    tool_database: Path,
) -> None:
    """Persist the complete declarative runtime configuration."""

    SQLiteWorkflowRepository(workflow_database).save(create_workflow())

    SQLiteModelRepository(model_database).save(create_model())

    tool_repository = SQLiteToolRepository(tool_database)

    tool_repository.save_definition(create_tool_definition())

    tool_repository.save_implementation(create_tool_implementation())


def reconstruct_runtime(
    *,
    workflow_database: Path,
    model_database: Path,
    tool_database: Path,
) -> AzathothRuntime:
    """Reconstruct runtime configuration after process restart."""

    workflows = WorkflowCatalogLoader(SQLiteWorkflowRepository(workflow_database)).load_catalog()

    models = ModelCatalogLoader(SQLiteModelRepository(model_database)).load_catalog()

    tool_loader = ToolCatalogLoader(SQLiteToolRepository(tool_database))

    tools = tool_loader.load_catalog()

    tool_implementations = tool_loader.load_implementation_catalog()

    language_models = LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model="example",
                response_text="success",
            ),
        }
    )

    return AzathothRuntime(
        workflows=workflows,
        models=models,
        language_models=language_models,
        tools=tools,
        tool_implementations=tool_implementations,
    )


def test_reconstructed_runtime_restores_complete_configuration(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"
    tool_database = tmp_path / "tools.db"

    persist_configuration(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    runtime = reconstruct_runtime(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    assert runtime.workflows.identifiers == (WORKFLOW_ID,)

    assert runtime.models.identifiers == (MODEL_IDENTIFIER,)

    assert runtime.tools.definitions == (create_tool_definition(),)

    assert runtime.tool_implementations.implementations == (create_tool_implementation(),)


def test_reconstructed_runtime_generates_workflow_candidate_by_id(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"
    tool_database = tmp_path / "tools.db"

    persist_configuration(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    runtime = reconstruct_runtime(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    candidate = runtime.generate_workflow_candidate(WORKFLOW_ID)

    assert candidate.metadata.id == WORKFLOW_ID

    assert tuple(step.id for step in candidate.steps) == (
        PROMPT_STEP_ID,
        TOOL_STEP_ID,
    )


def test_reconstructed_runtime_executes_prompt_and_tool_steps(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"
    tool_database = tmp_path / "tools.db"

    persist_configuration(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    runtime = reconstruct_runtime(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    candidate = runtime.generate_workflow_candidate(WORKFLOW_ID)

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    assert run.succeeded

    assert len(run.steps) == 2

    prompt_step = run.steps[0]
    tool_step = run.steps[1]

    assert prompt_step.execution is not None

    assert prompt_step.execution.output == "success"

    assert prompt_step.execution.metrics is not None

    assert prompt_step.execution.metrics.provider == "test"

    assert prompt_step.execution.metrics.model == "example"

    assert tool_step.execution is not None

    assert tool_step.execution.output == {
        "status": "tool success",
    }


def test_reconstructed_runtime_execution_uses_reconstructed_metadata(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"
    tool_database = tmp_path / "tools.db"

    persist_configuration(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    runtime = reconstruct_runtime(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    candidate = runtime.generate_workflow_candidate(WORKFLOW_ID)

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    assert run.workflow.id == WORKFLOW_ID
    assert run.workflow.name == "reconstructed runtime workflow"
    assert run.workflow.version == "1.0.0"

    assert run.steps[0].step_id == PROMPT_STEP_ID
    assert run.steps[1].step_id == TOOL_STEP_ID


def test_reconstructed_runtime_remains_process_local(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"
    tool_database = tmp_path / "tools.db"

    persist_configuration(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    first = reconstruct_runtime(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    second = reconstruct_runtime(
        workflow_database=workflow_database,
        model_database=model_database,
        tool_database=tool_database,
    )

    assert first is not second

    assert first.workflows == second.workflows
    assert first.models == second.models
    assert first.tools == second.tools
    assert first.tool_implementations == second.tool_implementations

    assert first.language_models is not second.language_models

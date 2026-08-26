"""End-to-end execution of persisted workflows and tools."""

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
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    SQLiteToolRepository,
    ToolCatalogLoader,
    ToolDefinition,
    ToolImplementation,
    ToolImplementationResolver,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
    ToolResolver,
)
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    ToolStepSpecification,
    WorkflowCatalogLoader,
    WorkflowCondition,
    WorkflowConditionOperator,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    WorkflowValueBinding,
    WorkflowValueReference,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

PRODUCER_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
TOOL_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
LONG_BRANCH_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")
SHORT_BRANCH_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

PRODUCER_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")
LONG_BRANCH_STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")
SHORT_BRANCH_STRATEGY_ID = UUID("88888888-8888-8888-8888-888888888888")

TOOL_ID = UUID("99999999-9999-9999-9999-999999999999")
IMPLEMENTATION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

MODEL_PROVIDER = "deterministic"
MODEL_NAME = "persisted-workflow-model"
MODEL_IDENTIFIER = f"{MODEL_PROVIDER}/{MODEL_NAME}"


def create_prompt_specification(
    *,
    strategy_id: UUID,
    name: str,
    prompt_text: str,
) -> PromptStrategySpec:
    """Create one deterministic prompt-backed step specification."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Execute the {name} workflow step.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text=prompt_text,
        ),
        model_selection=PortfolioModelSelection(
            requirements=ModelRequirements(),
        ),
    )


def create_workflow_specification() -> WorkflowSpecification:
    """Create a workflow routed by a deterministic tool result."""

    word_count_reference = WorkflowValueReference(
        producer_step_id=TOOL_STEP_ID,
        name="word_count",
    )

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Persisted workflow execution",
            description=("Execute a reconstructed workflow using a reconstructed tool."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=PRODUCER_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=PRODUCER_STRATEGY_ID,
                    name="produce text",
                    prompt_text="Produce deterministic source text.",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="text",
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=TOOL_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="word_count",
                        version="1.0.0",
                        runtime="python",
                    ),
                ),
                depends_on=(PRODUCER_STEP_ID,),
                inputs=(
                    WorkflowInputBinding(
                        name="text",
                        source=WorkflowValueReference(
                            producer_step_id=PRODUCER_STEP_ID,
                            name="text",
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
            WorkflowStepSpecification(
                id=LONG_BRANCH_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=LONG_BRANCH_STRATEGY_ID,
                    name="long branch",
                    prompt_text="Execute the long-input branch.",
                ),
                depends_on=(TOOL_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=word_count_reference,
                        operator=(WorkflowConditionOperator.GREATER_THAN_OR_EQUAL),
                        expected=4,
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="route",
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=SHORT_BRANCH_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=SHORT_BRANCH_STRATEGY_ID,
                    name="short branch",
                    prompt_text="Execute the short-input branch.",
                ),
                depends_on=(TOOL_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=word_count_reference,
                        operator=WorkflowConditionOperator.LESS_THAN,
                        expected=4,
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="route",
                    ),
                ),
            ),
        ),
    )


def create_tool_definition() -> ToolDefinition:
    """Create the durable word-count capability."""

    return ToolDefinition(
        id=TOOL_ID,
        name="word_count",
        description="Count whitespace-separated words.",
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
    )


def create_tool_implementation() -> ToolImplementation:
    """Create persisted executable source for the word-count capability."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        source=("def run(text):\n    return {'word_count': len(text.split())}\n"),
    )


def create_model_catalog() -> ModelCatalog:
    """Create deterministic model metadata for prompt-backed steps."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider=MODEL_PROVIDER,
                model=MODEL_NAME,
                display_name="Persisted Workflow Model",
                context_window_tokens=8_192,
            ),
        ),
    )


def create_model_registry() -> LanguageModelRegistry:
    """Create the deterministic runtime model registry."""

    return LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider=MODEL_PROVIDER,
                model=MODEL_NAME,
                response_text="one two three four",
            ),
        },
    )


def persist_workflow_and_tool(
    *,
    workflow_database: Path,
    tool_database: Path,
) -> None:
    """Persist every durable artifact required for workflow execution."""

    SQLiteWorkflowRepository(workflow_database).save(create_workflow_specification())

    tool_repository = SQLiteToolRepository(tool_database)

    tool_repository.save_definition(create_tool_definition())
    tool_repository.save_implementation(create_tool_implementation())


def load_persisted_workflow(
    workflow_database: Path,
) -> WorkflowSpecification:
    """Reconstruct and load the persisted workflow specification."""

    repository = SQLiteWorkflowRepository(workflow_database)

    catalog = WorkflowCatalogLoader(repository).load_catalog()

    specification = catalog.get(WORKFLOW_ID)

    assert specification is not None

    return specification


def test_persisted_workflow_and_tool_execute_after_reconstruction(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    tool_database = tmp_path / "tools.db"

    original_workflow = create_workflow_specification()

    persist_workflow_and_tool(
        workflow_database=workflow_database,
        tool_database=tool_database,
    )

    persisted_workflow = load_persisted_workflow(workflow_database)

    reconstructed_tool_repository = SQLiteToolRepository(tool_database)
    tool_loader = ToolCatalogLoader(reconstructed_tool_repository)

    tool_catalog = tool_loader.load_catalog()
    implementation_catalog = tool_loader.load_implementation_catalog()

    candidate = generate_workflow_candidate(
        specification=persisted_workflow,
        catalog=create_model_catalog(),
        registry=create_model_registry(),
        tool_resolver=ToolResolver(tool_catalog),
        tool_implementation_resolver=(ToolImplementationResolver(implementation_catalog)),
    )

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    assert persisted_workflow == original_workflow
    assert persisted_workflow is not original_workflow

    assert run.workflow == persisted_workflow.metadata

    assert len(run.steps) == 4

    producer_step = run.steps[0]
    tool_step = run.steps[1]
    long_branch_step = run.steps[2]
    short_branch_step = run.steps[3]

    assert producer_step.status is WorkflowStepStatus.EXECUTED
    assert tool_step.status is WorkflowStepStatus.EXECUTED
    assert long_branch_step.status is WorkflowStepStatus.EXECUTED
    assert short_branch_step.status is WorkflowStepStatus.SKIPPED

    assert producer_step.execution is not None
    assert producer_step.execution.output == "one two three four"

    assert tool_step.execution is not None
    assert tool_step.execution.output == {
        "word_count": 4,
    }

    word_count_values = run.values_named("word_count")

    assert len(word_count_values) == 1
    assert word_count_values[0].producer_step_id == TOOL_STEP_ID
    assert word_count_values[0].value == 4


def test_persisted_execution_uses_reconstructed_tool_source(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    tool_database = tmp_path / "tools.db"

    persist_workflow_and_tool(
        workflow_database=workflow_database,
        tool_database=tool_database,
    )

    workflow_catalog = WorkflowCatalogLoader(
        SQLiteWorkflowRepository(workflow_database)
    ).load_catalog()

    tool_loader = ToolCatalogLoader(SQLiteToolRepository(tool_database))

    specification = workflow_catalog.get(WORKFLOW_ID)

    assert specification is not None

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_model_catalog(),
        registry=create_model_registry(),
        tool_resolver=ToolResolver(tool_loader.load_catalog()),
        tool_implementation_resolver=(
            ToolImplementationResolver(tool_loader.load_implementation_catalog())
        ),
    )

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    assert run.values_named("word_count")[0].value == 4

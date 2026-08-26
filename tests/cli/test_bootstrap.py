"""Tests for Azathoth CLI runtime bootstrap."""

from pathlib import Path
from uuid import UUID

from pydantic import SecretStr

from azathoth.cli import (
    CliRuntimeConfiguration,
    load_runtime,
)
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelMetadata,
    ModelRequirements,
    Prompt,
    SQLiteModelRepository,
)
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    SQLiteToolRepository,
    ToolDefinition,
    ToolImplementation,
    ToolInputSchema,
    ToolOutputSchema,
)
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

TOOL_ID = UUID("44444444-4444-4444-4444-444444444444")

IMPLEMENTATION_ID = UUID("55555555-5555-5555-5555-555555555555")

OPENROUTER_IDENTIFIER = "openrouter/example/model"


def create_workflow() -> WorkflowSpecification:
    """Create one durable workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="CLI workflow",
            description="Exercise CLI runtime bootstrap.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="CLI prompt",
                        description=("Exercise reconstructed model configuration."),
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


def create_model() -> ModelMetadata:
    """Create one durable OpenRouter model."""

    return ModelMetadata(
        provider="openrouter",
        model="example/model",
        display_name="Example Model",
        context_window_tokens=8_192,
    )


def create_tool_definition() -> ToolDefinition:
    """Create one durable tool definition."""

    return ToolDefinition(
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
    )


def create_tool_implementation() -> ToolImplementation:
    """Create one durable tool implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        source=("def run(inputs):\n    return inputs\n"),
    )


def persist_configuration(
    database: Path,
) -> None:
    """Persist all durable CLI runtime configuration into one database."""

    SQLiteWorkflowRepository(database).save(create_workflow())

    SQLiteModelRepository(database).save(create_model())

    tools = SQLiteToolRepository(database)

    tools.save_definition(create_tool_definition())

    tools.save_implementation(create_tool_implementation())


def test_cli_bootstrap_reconstructs_workflow_catalog(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(CliRuntimeConfiguration(database=database))

    assert runtime.workflows.identifiers == (WORKFLOW_ID,)


def test_cli_bootstrap_reconstructs_model_catalog(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(CliRuntimeConfiguration(database=database))

    assert runtime.models.identifiers == (OPENROUTER_IDENTIFIER,)


def test_cli_bootstrap_reconstructs_tool_catalogs(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(CliRuntimeConfiguration(database=database))

    assert runtime.tools.definitions == (create_tool_definition(),)

    assert runtime.tool_implementations.implementations == (create_tool_implementation(),)


def test_cli_bootstrap_without_api_key_keeps_models_non_executable(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(CliRuntimeConfiguration(database=database))

    assert runtime.models.identifiers == (OPENROUTER_IDENTIFIER,)

    assert runtime.language_models.identifiers == ()


def test_cli_bootstrap_attaches_openrouter_models_when_configured(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
            openrouter_api_key=SecretStr("test-secret-key"),
        )
    )

    assert runtime.language_models.identifiers == (OPENROUTER_IDENTIFIER,)


def test_cli_bootstrap_handles_empty_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "empty.db"

    runtime = load_runtime(CliRuntimeConfiguration(database=database))

    assert runtime.workflows.identifiers == ()
    assert runtime.models.identifiers == ()
    assert runtime.language_models.identifiers == ()
    assert runtime.tools.definitions == ()
    assert runtime.tool_implementations.implementations == ()


def test_cli_bootstrap_uses_one_database_for_all_durable_configuration(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
            openrouter_api_key=SecretStr("test-secret-key"),
        )
    )

    assert runtime.workflows.identifiers == (WORKFLOW_ID,)

    assert runtime.models.identifiers == (OPENROUTER_IDENTIFIER,)

    assert runtime.language_models.identifiers == (OPENROUTER_IDENTIFIER,)

    assert runtime.tools.definitions == (create_tool_definition(),)

    assert runtime.tool_implementations.implementations == (create_tool_implementation(),)

"""Tests for Azathoth CLI runtime bootstrap."""

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import SecretStr

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
    ModelMetadata,
    ModelPortfolioEntry,
    ModelRequirements,
    Prompt,
    ProviderModel,
    SQLiteModelPortfolioRepository,
    SQLiteModelRepository,
    SQLiteProviderModelObservationRepository,
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

TOOL_ID = UUID("44444444-4444-4444-4444-444444444444")

IMPLEMENTATION_ID = UUID("55555555-5555-5555-5555-555555555555")

OPENROUTER_IDENTIFIER = "openrouter/example/model"


class FakeOpenRouterModelDirectory:
    """Provide deterministic current OpenRouter state for bootstrap tests."""

    def __init__(
        self,
        configuration: object,
    ) -> None:
        self._configuration = configuration

    @property
    def provider(
        self,
    ) -> str:
        """Return the OpenRouter provider identity."""

        return "openrouter"

    async def models(
        self,
    ) -> tuple[ProviderModel, ...]:
        """Return deterministic current OpenRouter model state."""

        return (create_provider_model(),)

    async def model(
        self,
        identifier: str,
    ) -> ProviderModel | None:
        """Return one deterministic current OpenRouter model."""

        model = create_provider_model()

        if identifier != model.model:
            return None

        return model


def create_workflow() -> WorkflowSpecification:
    """Create one durable workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="CLI workflow",
            description=("Exercise CLI runtime bootstrap."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="CLI prompt",
                        description=("Exercise current model discovery."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=(
                        PortfolioModelSelection(
                            requirements=ModelRequirements(),
                        )
                    ),
                ),
            ),
        ),
    )


def create_production_state() -> WorkflowProductionState:
    """Create one durable active production workflow state."""

    configured = create_workflow()

    prompt = configured.steps[0].specification

    assert isinstance(
        prompt,
        PromptStrategySpec,
    )

    production_prompt = prompt.model_copy(
        update={
            "model_selection": FixedModelSelection(
                provider="openrouter",
                model="example/model",
            ),
        }
    )

    production_step = configured.steps[0].model_copy(
        update={
            "specification": production_prompt,
        }
    )

    production = configured.model_copy(
        update={
            "steps": (production_step,),
        }
    )

    return WorkflowProductionState(
        specification=production,
    )


def create_provider_model() -> ProviderModel:
    """Create deterministic current OpenRouter model state."""

    return ProviderModel(
        provider="openrouter",
        model="example/model",
        display_name="Example Model",
        context_window_tokens=8_192,
    )


def create_stale_model_metadata() -> ModelMetadata:
    """Create persisted metadata that must not establish availability."""

    return ModelMetadata(
        provider="openrouter",
        model="stale/model",
        display_name="Stale Model",
        context_window_tokens=4_096,
    )


def create_tool_definition() -> ToolDefinition:
    """Create one durable tool definition."""

    return ToolDefinition(
        id=TOOL_ID,
        name="example tool",
        description=("Execute one deterministic example tool."),
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
    """Persist durable CLI runtime configuration."""

    SQLiteWorkflowRepository(database).save(create_workflow())

    SQLiteWorkflowProductionStateRepository(database).set(create_production_state())

    SQLiteModelPortfolioRepository(database).save(
        ModelPortfolioEntry(
            provider="openrouter",
            model="example/model",
        )
    )

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


def test_cli_bootstrap_without_provider_credentials_has_no_current_models(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(CliRuntimeConfiguration(database=database))

    assert runtime.models.identifiers == ()

    assert runtime.language_models.identifiers == ()


def test_cli_bootstrap_does_not_treat_persisted_metadata_as_current(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    stale = create_stale_model_metadata()

    SQLiteModelRepository(database).save(stale)

    runtime = load_runtime(CliRuntimeConfiguration(database=database))

    assert stale.identifier not in (runtime.models.identifiers)


def test_cli_bootstrap_discovers_current_openrouter_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    monkeypatch.setattr(
        "azathoth.cli.bootstrap.OpenRouterModelDirectory",
        FakeOpenRouterModelDirectory,
    )

    runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
            openrouter_api_key=SecretStr("test-secret-key"),
        )
    )

    assert runtime.models.identifiers == (OPENROUTER_IDENTIFIER,)


def test_cli_bootstrap_records_current_provider_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    monkeypatch.setattr(
        "azathoth.cli.bootstrap.OpenRouterModelDirectory",
        FakeOpenRouterModelDirectory,
    )

    load_runtime(
        CliRuntimeConfiguration(
            database=database,
            openrouter_api_key=SecretStr("test-secret-key"),
        )
    )

    repository = SQLiteProviderModelObservationRepository(database)

    observations = repository.observations_for_model(OPENROUTER_IDENTIFIER)

    assert len(observations) == 1
    assert observations[0].model == create_provider_model()


def test_cli_bootstrap_reuses_unchanged_provider_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    monkeypatch.setattr(
        "azathoth.cli.bootstrap.OpenRouterModelDirectory",
        FakeOpenRouterModelDirectory,
    )

    configuration = CliRuntimeConfiguration(
        database=database,
        openrouter_api_key=SecretStr("test-secret-key"),
    )

    first = load_runtime(configuration)
    second = load_runtime(configuration)

    repository = SQLiteProviderModelObservationRepository(database)

    assert first.models == second.models
    assert len(repository.observations_for_model(OPENROUTER_IDENTIFIER)) == 1


def test_cli_bootstrap_reconstructs_tool_catalogs(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(CliRuntimeConfiguration(database=database))

    assert runtime.tools.definitions == (create_tool_definition(),)

    assert runtime.tool_implementations.implementations == (create_tool_implementation(),)


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
    assert runtime.portfolio.identifiers == ()
    assert runtime.production_states == ()


def test_cli_bootstrap_uses_one_database_for_durable_state_and_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    monkeypatch.setattr(
        "azathoth.cli.bootstrap.OpenRouterModelDirectory",
        FakeOpenRouterModelDirectory,
    )

    runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
            openrouter_api_key=SecretStr("test-secret-key"),
        )
    )

    observations = SQLiteProviderModelObservationRepository(database).observations_for_model(
        OPENROUTER_IDENTIFIER
    )

    assert runtime.workflows.identifiers == (WORKFLOW_ID,)

    assert runtime.models.identifiers == (OPENROUTER_IDENTIFIER,)

    assert runtime.language_models.identifiers == (OPENROUTER_IDENTIFIER,)

    assert runtime.tools.definitions == (create_tool_definition(),)

    assert runtime.tool_implementations.implementations == (create_tool_implementation(),)

    assert runtime.portfolio.identifiers == (OPENROUTER_IDENTIFIER,)

    assert len(observations) == 1


def test_cli_bootstrap_reconstructs_model_portfolio(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(CliRuntimeConfiguration(database=database))

    assert runtime.portfolio.identifiers == (OPENROUTER_IDENTIFIER,)


def test_cli_bootstrap_reconstructs_production_workflow_state(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    persist_configuration(database)

    runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    assert runtime.production_states == (create_production_state(),)

    assert (
        runtime.production_state(
            WORKFLOW_ID,
        )
        == create_production_state()
    )

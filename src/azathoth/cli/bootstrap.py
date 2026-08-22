"""Bootstrap Azathoth runtime composition for the command-line application."""

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelCatalogLoader,
    OpenRouterConfiguration,
    OpenRouterModelRegistryLoader,
    SQLiteModelRepository,
)
from azathoth.runtime import AzathothRuntime
from azathoth.tools import (
    SQLiteToolRepository,
    ToolCatalogLoader,
)
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowCatalogLoader,
)


def load_runtime(
    configuration: CliRuntimeConfiguration,
) -> AzathothRuntime:
    """Reconstruct durable configuration and compose an executable runtime."""

    workflows = WorkflowCatalogLoader(
        SQLiteWorkflowRepository(configuration.database)
    ).load_catalog()

    models = ModelCatalogLoader(SQLiteModelRepository(configuration.database)).load_catalog()

    tool_loader = ToolCatalogLoader(SQLiteToolRepository(configuration.database))

    tools = tool_loader.load_catalog()

    tool_implementations = tool_loader.load_implementation_catalog()

    language_models = _load_language_models(
        configuration=configuration,
        models=models,
    )

    return AzathothRuntime(
        workflows=workflows,
        models=models,
        language_models=language_models,
        tools=tools,
        tool_implementations=tool_implementations,
    )


def _load_language_models(
    *,
    configuration: CliRuntimeConfiguration,
    models: ModelCatalog,
) -> LanguageModelRegistry:
    """Construct executable provider implementations for configured models."""

    if configuration.openrouter_api_key is None:
        return LanguageModelRegistry()

    openrouter = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(api_key=configuration.openrouter_api_key)
    ).load_registry(models)

    return LanguageModelRegistry.compose((openrouter,))

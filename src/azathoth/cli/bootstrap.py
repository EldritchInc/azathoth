"""Bootstrap Azathoth runtime composition for the command-line application."""

import asyncio

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolioLoader,
    OpenRouterConfiguration,
    OpenRouterModelDirectory,
    OpenRouterModelRegistryLoader,
    ProviderModelCatalogSynchronizer,
    ProviderModelObserver,
)
from azathoth.runtime import AzathothRuntime
from azathoth.tools import (
    ToolCatalogLoader,
)
from azathoth.workflows import (
    WorkflowCatalogLoader,
)


def load_runtime(
    configuration: CliRuntimeConfiguration,
) -> AzathothRuntime:
    """Reconstruct durable configuration and compose an executable runtime.

    The semantic judge rotation is loaded but not resolved: judges are checked
    only when a command asks the runtime for semantic judging, so an unusable
    judge never blocks commands that do not judge semantically.
    """

    workflows = WorkflowCatalogLoader(repositories(configuration).workflows).load_catalog()

    production_states = repositories(configuration).production_states.states()

    models = _load_current_models(configuration)

    portfolio = ModelPortfolioLoader(repositories(configuration).portfolio).load_portfolio()

    tool_loader = ToolCatalogLoader(repositories(configuration).tools)

    tools = tool_loader.load_catalog()

    tool_implementations = tool_loader.load_implementation_catalog()

    language_models = _load_language_models(
        configuration=configuration,
        models=models,
    )

    return AzathothRuntime(
        workflows=workflows,
        production_states=production_states,
        models=models,
        portfolio=portfolio,
        language_models=language_models,
        tools=tools,
        tool_implementations=tool_implementations,
        judges=repositories(configuration).judges.rotation(),
    )


def _load_current_models(
    configuration: CliRuntimeConfiguration,
) -> ModelCatalog:
    """Return current provider model state for runtime composition."""

    if configuration.openrouter_api_key is None:
        return ModelCatalog()

    provider_configuration = OpenRouterConfiguration(api_key=configuration.openrouter_api_key)

    observer = ProviderModelObserver(
        directory=OpenRouterModelDirectory(provider_configuration),
        repository=repositories(configuration).provider_observations,
    )

    synchronizer = ProviderModelCatalogSynchronizer(observers=(observer,))

    return asyncio.run(synchronizer.synchronize())


def _load_language_models(
    *,
    configuration: CliRuntimeConfiguration,
    models: ModelCatalog,
) -> LanguageModelRegistry:
    """Construct executable provider implementations for current models."""

    if configuration.openrouter_api_key is None:
        return LanguageModelRegistry()

    provider_configuration = OpenRouterConfiguration(api_key=configuration.openrouter_api_key)

    openrouter = OpenRouterModelRegistryLoader(provider_configuration).load_registry(models)

    return LanguageModelRegistry.compose((openrouter,))

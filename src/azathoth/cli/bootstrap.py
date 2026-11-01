"""Bootstrap Azathoth runtime composition for the command-line application."""

import asyncio

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.providers import (
    BedrockClient,
    BedrockConfiguration,
    BedrockDriver,
    BedrockModelDirectory,
    BedrockModelRegistryLoader,
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolioLoader,
    OpenRouterConfiguration,
    OpenRouterModelDirectory,
    OpenRouterModelRegistryLoader,
    ProviderModelCatalogSynchronizer,
    ProviderModelObserver,
    boto3_driver,
    configure_bedrock,
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
    """Return current provider model state for runtime composition.

    Every provider that is on contributes its models: OpenRouter when its key
    is set, and Bedrock when `AZATHOTH_BEDROCK` is (ADR 0103). With neither,
    the catalog is empty.

    Raises:
        ModelDiscoveryError: A provider that is on could not be discovered.
        BedrockUnavailableError: Bedrock is on without the `bedrock` extra.
        BedrockConfigurationError: Bedrock is on without a region, or with a
            pricing document that cannot be used.
    """

    observers: list[ProviderModelObserver] = []

    if configuration.openrouter_api_key is not None:
        provider_configuration = OpenRouterConfiguration(api_key=configuration.openrouter_api_key)

        observers.append(
            ProviderModelObserver(
                directory=OpenRouterModelDirectory(provider_configuration),
                repository=repositories(configuration).provider_observations,
            )
        )

    bedrock = _bedrock(configuration)

    if bedrock is not None:
        bedrock_configuration, client = bedrock

        observers.append(
            ProviderModelObserver(
                directory=BedrockModelDirectory(bedrock_configuration, client),
                repository=repositories(configuration).provider_observations,
            )
        )

    if not observers:
        return ModelCatalog()

    synchronizer = ProviderModelCatalogSynchronizer(observers=observers)

    return asyncio.run(synchronizer.synchronize())


def _load_language_models(
    *,
    configuration: CliRuntimeConfiguration,
    models: ModelCatalog,
) -> LanguageModelRegistry:
    """Construct executable provider implementations for current models."""

    registries: list[LanguageModelRegistry] = []

    if configuration.openrouter_api_key is not None:
        provider_configuration = OpenRouterConfiguration(api_key=configuration.openrouter_api_key)

        registries.append(
            OpenRouterModelRegistryLoader(provider_configuration).load_registry(models)
        )

    bedrock = _bedrock(configuration)

    if bedrock is not None:
        _, client = bedrock

        registries.append(BedrockModelRegistryLoader(client).load_registry(models))

    if not registries:
        return LanguageModelRegistry()

    return LanguageModelRegistry.compose(registries)


def _bedrock(
    configuration: CliRuntimeConfiguration,
) -> tuple[BedrockConfiguration, BedrockClient] | None:
    """Return Bedrock's configuration and a client for it, or None when Bedrock is off."""

    if not configuration.bedrock_enabled:
        return None

    driver = _bedrock_driver()

    bedrock_configuration = configure_bedrock(
        dict(configuration.bedrock_environment),
        driver=driver,
    )

    assert bedrock_configuration is not None

    return bedrock_configuration, driver.client(bedrock_configuration)


def _bedrock_driver() -> BedrockDriver:
    """Return the driver that reaches Bedrock: boto3's.

    Raises:
        BedrockUnavailableError: The `bedrock` extra is not installed.
    """

    return boto3_driver()

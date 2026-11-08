"""Which model providers an instance reaches (ADR 0120).

An instance reaches no provider unless it is given `ProviderSettings`, and
reaches those only when a call needs to know what they serve: opening never
imports boto3 or calls a provider.
"""

import os
from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict, SecretStr

from azathoth.api.errors import ProviderConfigurationError
from azathoth.providers import (
    AWS_DEFAULT_REGION_VARIABLE,
    AWS_REGION_VARIABLE,
    BEDROCK_ENABLED_VARIABLE,
    BEDROCK_PRICING_VARIABLE,
    BedrockClient,
    BedrockConfiguration,
    BedrockConfigurationError,
    BedrockModelDirectory,
    BedrockModelRegistryLoader,
    BedrockUnavailableError,
    LanguageModelRegistry,
    ModelCatalog,
    OpenRouterConfiguration,
    OpenRouterModelDirectory,
    OpenRouterModelRegistryLoader,
    ProviderModelDirectory,
    bedrock_enabled,
    boto3_driver,
    configure_bedrock,
)

OPENROUTER_API_KEY_VARIABLE: Final = "OPENROUTER_API_KEY"
"""The variable whose value is the OpenRouter API key."""

BEDROCK_VARIABLES: Final = (
    BEDROCK_ENABLED_VARIABLE,
    BEDROCK_PRICING_VARIABLE,
    AWS_REGION_VARIABLE,
    AWS_DEFAULT_REGION_VARIABLE,
)
"""The variables that configure Bedrock (ADR 0103); boto3 finds AWS's credentials itself."""


class ProviderSettings(BaseModel):
    """The providers an instance may ask for models, and how to reach them.

    OpenRouter is on when it has a key. Bedrock is on when its environment
    turns it on, as `AZATHOTH_BEDROCK` does for the command line. With
    neither, an instance serves no models.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    openrouter_api_key: SecretStr | None = None

    bedrock_environment: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "ProviderSettings":
        """Return the settings the environment gives, as the command line reads them.

        An empty `OPENROUTER_API_KEY` leaves OpenRouter off. The Bedrock
        variables are kept only while `AZATHOTH_BEDROCK` turns Bedrock on.
        """

        values = os.environ if environment is None else environment

        key = values.get(OPENROUTER_API_KEY_VARIABLE)

        return cls(
            openrouter_api_key=SecretStr(key) if key else None,
            bedrock_environment=(
                tuple((name, values[name]) for name in BEDROCK_VARIABLES if name in values)
                if bedrock_enabled(values)
                else ()
            ),
        )


def model_directories(
    settings: ProviderSettings,
) -> tuple[ProviderModelDirectory, ...]:
    """Return the directory of each provider the settings turn on, OpenRouter first.

    Raises:
        ProviderConfigurationError: Bedrock is on without the `bedrock`
            extra, without a region, or with a pricing document that cannot
            be used.
    """

    directories: list[ProviderModelDirectory] = []

    if settings.openrouter_api_key is not None:
        directories.append(
            OpenRouterModelDirectory(
                OpenRouterConfiguration(api_key=settings.openrouter_api_key),
            )
        )

    bedrock = _bedrock(settings)

    if bedrock is not None:
        configuration, client = bedrock
        directories.append(BedrockModelDirectory(configuration, client))

    return tuple(directories)


def language_models(
    settings: ProviderSettings,
    models: ModelCatalog,
) -> LanguageModelRegistry:
    """Return the executable models the settings' providers serve, for the models discovered.

    Raises:
        ProviderConfigurationError: Bedrock is configured in a way that
            cannot be used.
    """

    registries: list[LanguageModelRegistry] = []

    if settings.openrouter_api_key is not None:
        registries.append(
            OpenRouterModelRegistryLoader(
                OpenRouterConfiguration(api_key=settings.openrouter_api_key),
            ).load_registry(models)
        )

    bedrock = _bedrock(settings)

    if bedrock is not None:
        _, client = bedrock
        registries.append(BedrockModelRegistryLoader(client).load_registry(models))

    if not registries:
        return LanguageModelRegistry()

    return LanguageModelRegistry.compose(registries)


def _bedrock(
    settings: ProviderSettings,
) -> tuple[BedrockConfiguration, BedrockClient] | None:
    """Return Bedrock's configuration and a client for it, or None when Bedrock is off.

    Raises:
        ProviderConfigurationError: Bedrock is on without the `bedrock`
            extra, without a region, or with a pricing document that cannot
            be used.
    """

    environment = dict(settings.bedrock_environment)

    if not bedrock_enabled(environment):
        return None

    try:
        driver = boto3_driver()
        configuration = configure_bedrock(environment, driver=driver)
    except (BedrockUnavailableError, BedrockConfigurationError) as exc:
        raise ProviderConfigurationError(str(exc)) from exc

    assert configuration is not None

    return configuration, driver.client(configuration)


__all__ = [
    "BEDROCK_VARIABLES",
    "OPENROUTER_API_KEY_VARIABLE",
    "ProviderSettings",
    "language_models",
    "model_directories",
]

"""OpenRouter runtime assembly for configured model catalogs."""

import httpx

from azathoth.providers.catalog import ModelCatalog
from azathoth.providers.openrouter import OpenRouterLanguageModel
from azathoth.providers.openrouter_models import OpenRouterConfiguration
from azathoth.providers.registry import LanguageModelRegistry


class OpenRouterModelRegistryLoader:
    """Build executable OpenRouter models from catalog metadata."""

    def __init__(
        self,
        configuration: OpenRouterConfiguration,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._configuration = configuration
        self._transport = transport

    def load_registry(
        self,
        catalog: ModelCatalog,
    ) -> LanguageModelRegistry:
        """Build a registry for every OpenRouter model in the catalog."""

        models = {
            metadata.identifier: OpenRouterLanguageModel(
                self._configuration,
                metadata.model,
                transport=self._transport,
            )
            for metadata in catalog.models_for_provider("openrouter")
        }

        return LanguageModelRegistry(models=models)

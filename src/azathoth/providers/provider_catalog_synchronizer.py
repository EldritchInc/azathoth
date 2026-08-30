"""Synchronize current provider model state into runtime catalogs."""

from collections.abc import Sequence

from azathoth.providers.catalog import ModelCatalog
from azathoth.providers.models import ModelMetadata
from azathoth.providers.provider_metadata import (
    model_metadata_from_provider_model,
)
from azathoth.providers.provider_observer import (
    ProviderModelObserver,
)


class ProviderModelCatalogSynchronizer:
    """Build runtime catalogs from current provider model discovery."""

    def __init__(
        self,
        observers: Sequence[ProviderModelObserver],
    ) -> None:
        self._observers = tuple(observers)

    async def synchronize(
        self,
    ) -> ModelCatalog:
        """Observe current providers and return their current model catalog."""

        models: list[ModelMetadata] = []
        identifiers: set[str] = set()

        for observer in self._observers:
            updates = await observer.observe_models()

            for update in updates:
                provider_model = update.observation.model

                if provider_model.identifier in identifiers:
                    raise ValueError(
                        "Current provider model "
                        f"{provider_model.identifier!r} "
                        "was discovered more than once."
                    )

                identifiers.add(provider_model.identifier)

                models.append(model_metadata_from_provider_model(provider_model))

        return ModelCatalog(models=tuple(models))

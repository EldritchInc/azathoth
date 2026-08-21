"""Reconstruct model catalogs from durable metadata repositories."""

from azathoth.providers.catalog import ModelCatalog
from azathoth.providers.repository import ModelRepository


class ModelCatalogLoader:
    """Load immutable model catalogs from repository state."""

    def __init__(
        self,
        repository: ModelRepository,
    ) -> None:
        self._repository = repository

    def load_catalog(
        self,
    ) -> ModelCatalog:
        """Reconstruct the configured model catalog."""

        return ModelCatalog(models=self._repository.models())

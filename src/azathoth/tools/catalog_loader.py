"""Hydrate immutable tool catalogs from a repository."""

from azathoth.tools.catalog import ToolCatalog
from azathoth.tools.implementation_catalog import (
    ToolImplementationCatalog,
)
from azathoth.tools.repository import ToolRepository


class ToolCatalogLoader:
    """Build immutable catalogs from persisted tool artifacts."""

    def __init__(
        self,
        repository: ToolRepository,
    ) -> None:
        self._repository = repository

    def load_catalog(
        self,
    ) -> ToolCatalog:
        """Load all persisted tool definitions."""

        return ToolCatalog(
            definitions=self._repository.definitions(),
        )

    def load_implementation_catalog(
        self,
    ) -> ToolImplementationCatalog:
        """Load all persisted tool implementations."""

        return ToolImplementationCatalog(
            implementations=self._repository.implementations(),
        )

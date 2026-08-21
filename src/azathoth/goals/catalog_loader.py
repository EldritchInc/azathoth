"""Reconstruct goal catalogs from durable repositories."""

from azathoth.goals.catalog import GoalCatalog
from azathoth.goals.repository import GoalRepository


class GoalCatalogLoader:
    """Load immutable goal catalogs from repository state."""

    def __init__(
        self,
        repository: GoalRepository,
    ) -> None:
        self._repository = repository

    def load_catalog(
        self,
    ) -> GoalCatalog:
        """Reconstruct the configured goal catalog."""

        return GoalCatalog(goals=self._repository.goals())

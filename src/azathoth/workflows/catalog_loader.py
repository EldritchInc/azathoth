"""Hydrate immutable workflow artifacts from a repository."""

from azathoth.workflows.catalog import WorkflowCatalog
from azathoth.workflows.repository import WorkflowRepository


class WorkflowCatalogLoader:
    """Build immutable workflow artifacts from persisted repository state."""

    def __init__(
        self,
        repository: WorkflowRepository,
    ) -> None:
        self._repository = repository

    def load_catalog(
        self,
    ) -> WorkflowCatalog:
        """Load all persisted workflow specifications."""

        return WorkflowCatalog(
            specifications=self._repository.specifications(),
        )

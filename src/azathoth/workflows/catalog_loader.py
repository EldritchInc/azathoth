"""Hydrate immutable workflow artifacts from a repository."""

from uuid import UUID

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
        """Load every workflow's latest specification and its revision number."""

        specifications = self._repository.specifications()

        revisions: dict[UUID, int] = {}

        for specification in specifications:
            revision = self._repository.latest_revision(
                specification.metadata.id,
            )

            if revision is not None:
                revisions[specification.metadata.id] = revision.number

        return WorkflowCatalog(
            specifications=specifications,
            revisions=revisions,
        )

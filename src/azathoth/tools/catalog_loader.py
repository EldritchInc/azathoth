"""Hydrate immutable tool artifacts from a repository."""

from uuid import UUID

from azathoth.tools.catalog import ToolCatalog
from azathoth.tools.implementation_catalog import (
    ToolImplementationCatalog,
)
from azathoth.tools.repository import ToolRepository
from azathoth.tools.testing import ToolTestCase


class ToolCatalogLoader:
    """Build immutable tool artifacts from persisted repository state."""

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

    def load_test_cases(
        self,
        tool_id: UUID | None = None,
    ) -> tuple[ToolTestCase, ...]:
        """Load persisted tool test cases, optionally filtered by tool."""

        test_cases = self._repository.test_cases()

        if tool_id is None:
            return test_cases

        return tuple(test_case for test_case in test_cases if test_case.tool_id == tool_id)

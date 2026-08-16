"""Deterministic resolution of tool requirements."""

from azathoth.tools.catalog import ToolCatalog
from azathoth.tools.definition import ToolDefinition
from azathoth.tools.matching import ToolMatcher
from azathoth.tools.requirements import ToolRequirement, ToolRequirements


class ToolResolver:
    """Resolve tool requirements against an immutable tool catalog."""

    def __init__(
        self,
        catalog: ToolCatalog,
        matcher: ToolMatcher | None = None,
    ) -> None:
        self._catalog = catalog
        self._matcher = matcher or ToolMatcher()

    def resolve(
        self,
        requirement: ToolRequirement,
    ) -> tuple[ToolDefinition, ...]:
        """Return definitions satisfying one tool requirement."""

        return tuple(
            definition
            for definition in self._catalog.definitions
            if self._matcher.matches(
                definition,
                requirement,
            )
        )

    def resolve_all(
        self,
        requirements: ToolRequirements,
    ) -> tuple[tuple[ToolDefinition, ...], ...]:
        """Resolve every requirement in declaration order."""

        return tuple(self.resolve(requirement) for requirement in requirements.requirements)

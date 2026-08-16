"""Deterministic resolution of tool implementations."""

from azathoth.tools.definition import ToolDefinition
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.implementation_catalog import ToolImplementationCatalog
from azathoth.tools.requirements import ToolRequirement


class ToolImplementationResolver:
    """Resolve implementations for durable tool definitions."""

    def __init__(
        self,
        catalog: ToolImplementationCatalog,
    ) -> None:
        self._catalog = catalog

    def resolve(
        self,
        definition: ToolDefinition,
    ) -> tuple[ToolImplementation, ...]:
        """Return implementations satisfying one exact tool definition."""

        return self._catalog.implementations_for_version(
            definition.id,
            definition.version,
        )

    def resolve_for_requirement(
        self,
        definition: ToolDefinition,
        requirement: ToolRequirement,
    ) -> tuple[ToolImplementation, ...]:
        """Return implementations satisfying implementation constraints."""

        implementations = self.resolve(definition)

        if requirement.runtime is None:
            return implementations

        return tuple(
            implementation
            for implementation in implementations
            if implementation.runtime == requirement.runtime
        )

    def resolve_all(
        self,
        definitions: tuple[ToolDefinition, ...],
    ) -> tuple[tuple[ToolImplementation, ...], ...]:
        """Resolve implementations for definitions in declaration order."""

        return tuple(self.resolve(definition) for definition in definitions)

    def resolve_all_for_requirement(
        self,
        definitions: tuple[ToolDefinition, ...],
        requirement: ToolRequirement,
    ) -> tuple[tuple[ToolImplementation, ...], ...]:
        """Resolve implementations for definitions using one requirement."""

        return tuple(
            self.resolve_for_requirement(
                definition,
                requirement,
            )
            for definition in definitions
        )

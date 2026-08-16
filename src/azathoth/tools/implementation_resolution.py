"""Deterministic resolution of tool implementations."""

from azathoth.tools.definition import ToolDefinition
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.implementation_catalog import ToolImplementationCatalog


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

    def resolve_all(
        self,
        definitions: tuple[ToolDefinition, ...],
    ) -> tuple[tuple[ToolImplementation, ...], ...]:
        """Resolve implementations for definitions in declaration order."""

        return tuple(self.resolve(definition) for definition in definitions)

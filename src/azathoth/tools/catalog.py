"""Immutable catalog of durable tool definitions."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from azathoth.tools.definition import ToolDefinition


class ToolCatalog(BaseModel):
    """A reproducible inventory of durable tool definitions."""

    model_config = ConfigDict(frozen=True)

    definitions: tuple[ToolDefinition, ...] = ()

    @model_validator(mode="after")
    def validate_unique_references(self) -> "ToolCatalog":
        """Reject duplicate tool identity and version references."""

        references = tuple((definition.id, definition.version) for definition in self.definitions)

        if len(references) != len(set(references)):
            raise ValueError("Tool catalog cannot contain duplicate tool references.")

        return self

    @property
    def references(self) -> tuple[tuple[UUID, str], ...]:
        """Return tool identity and version references in catalog order."""

        return tuple((definition.id, definition.version) for definition in self.definitions)

    def get(
        self,
        tool_id: UUID,
        version: str,
    ) -> ToolDefinition | None:
        """Return an exact version of a tool definition."""

        return next(
            (
                definition
                for definition in self.definitions
                if definition.id == tool_id and definition.version == version
            ),
            None,
        )

    def definitions_for(
        self,
        tool_id: UUID,
    ) -> tuple[ToolDefinition, ...]:
        """Return every definition version for one tool identity."""

        return tuple(definition for definition in self.definitions if definition.id == tool_id)

    def versions_for(
        self,
        tool_id: UUID,
    ) -> tuple[str, ...]:
        """Return versions for one tool identity in catalog order."""

        return tuple(definition.version for definition in self.definitions_for(tool_id))

    def definitions_named(
        self,
        name: str,
    ) -> tuple[ToolDefinition, ...]:
        """Return definitions with an exact tool name."""

        return tuple(definition for definition in self.definitions if definition.name == name)

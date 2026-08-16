"""Immutable catalog of durable tool implementations."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from azathoth.tools.implementation import ToolImplementation


class ToolImplementationCatalog(BaseModel):
    """A reproducible inventory of durable tool implementations."""

    model_config = ConfigDict(frozen=True)

    implementations: tuple[ToolImplementation, ...] = ()

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> "ToolImplementationCatalog":
        """Reject duplicate implementation identifiers."""

        identifiers = tuple(implementation.id for implementation in self.implementations)

        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Tool implementation catalog cannot contain duplicate identifiers.")

        return self

    @property
    def identifiers(self) -> tuple[UUID, ...]:
        """Return implementation identifiers in catalog order."""

        return tuple(implementation.id for implementation in self.implementations)

    def get(
        self,
        implementation_id: UUID,
    ) -> ToolImplementation | None:
        """Return an implementation by exact identifier."""

        return next(
            (
                implementation
                for implementation in self.implementations
                if implementation.id == implementation_id
            ),
            None,
        )

    def implementations_for(
        self,
        tool_id: UUID,
    ) -> tuple[ToolImplementation, ...]:
        """Return implementations for one tool identity."""

        return tuple(
            implementation
            for implementation in self.implementations
            if implementation.tool_id == tool_id
        )

    def implementations_for_version(
        self,
        tool_id: UUID,
        tool_version: str,
    ) -> tuple[ToolImplementation, ...]:
        """Return implementations for one exact tool definition version."""

        return tuple(
            implementation
            for implementation in self.implementations_for(tool_id)
            if implementation.tool_version == tool_version
        )

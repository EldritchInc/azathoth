"""Persistence contracts for durable tool artifacts."""

from typing import Protocol
from uuid import UUID

from azathoth.tools.definition import ToolDefinition
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.testing import ToolTestCase


class ToolRepository(Protocol):
    """Persist and retrieve durable tool artifacts."""

    def save_definition(
        self,
        definition: ToolDefinition,
    ) -> None:
        """Persist one tool definition."""

        ...

    def get_definition(
        self,
        definition_id: UUID,
    ) -> ToolDefinition | None:
        """Return a tool definition by identifier."""

        ...

    def definitions(self) -> tuple[ToolDefinition, ...]:
        """Return all persisted tool definitions in insertion order."""

        ...

    def save_implementation(
        self,
        implementation: ToolImplementation,
    ) -> None:
        """Persist one tool implementation."""

        ...

    def get_implementation(
        self,
        implementation_id: UUID,
    ) -> ToolImplementation | None:
        """Return a tool implementation by identifier."""

        ...

    def implementations(self) -> tuple[ToolImplementation, ...]:
        """Return all persisted tool implementations in insertion order."""

        ...

    def save_test_case(
        self,
        test_case: ToolTestCase,
    ) -> None:
        """Persist one tool test case."""

        ...

    def get_test_case(
        self,
        test_case_id: UUID,
    ) -> ToolTestCase | None:
        """Return a tool test case by identifier."""

        ...

    def test_cases(self) -> tuple[ToolTestCase, ...]:
        """Return all persisted tool test cases in insertion order."""

        ...

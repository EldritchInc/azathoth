"""Deterministic in-memory persistence for durable tool artifacts."""

from collections.abc import Mapping
from uuid import UUID

from azathoth.tools.definition import ToolDefinition
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.repository import ToolRepository
from azathoth.tools.testing import ToolTestCase

ToolDefinitionReference = tuple[UUID, str]


class InMemoryToolRepository:
    """Store durable tool artifacts in insertion order."""

    def __init__(self) -> None:
        self._definitions: dict[
            ToolDefinitionReference,
            ToolDefinition,
        ] = {}
        self._implementations: dict[UUID, ToolImplementation] = {}
        self._test_cases: dict[UUID, ToolTestCase] = {}

    def save_definition(
        self,
        definition: ToolDefinition,
    ) -> None:
        """Persist one exact tool definition version without replacement."""

        reference = (
            definition.id,
            definition.version,
        )

        if reference in self._definitions:
            raise ValueError(
                f"Tool definition {definition.id}@{definition.version} already exists."
            )

        self._definitions[reference] = definition

    def get_definition(
        self,
        tool_id: UUID,
        version: str,
    ) -> ToolDefinition | None:
        """Return one exact tool definition version."""

        return self._definitions.get(
            (
                tool_id,
                version,
            )
        )

    def definitions(self) -> tuple[ToolDefinition, ...]:
        """Return all persisted tool definitions in insertion order."""

        return tuple(self._definitions.values())

    def save_implementation(
        self,
        implementation: ToolImplementation,
    ) -> None:
        """Persist one tool implementation without replacing existing data."""

        self._reject_duplicate(
            artifact_name="tool implementation",
            artifact_id=implementation.id,
            existing=self._implementations,
        )

        self._implementations[implementation.id] = implementation

    def get_implementation(
        self,
        implementation_id: UUID,
    ) -> ToolImplementation | None:
        """Return a tool implementation by identifier."""

        return self._implementations.get(implementation_id)

    def implementations(self) -> tuple[ToolImplementation, ...]:
        """Return all persisted tool implementations in insertion order."""

        return tuple(self._implementations.values())

    def save_test_case(
        self,
        test_case: ToolTestCase,
    ) -> None:
        """Persist one tool test case without replacing existing data."""

        self._reject_duplicate(
            artifact_name="tool test case",
            artifact_id=test_case.id,
            existing=self._test_cases,
        )

        self._test_cases[test_case.id] = test_case

    def get_test_case(
        self,
        test_case_id: UUID,
    ) -> ToolTestCase | None:
        """Return a tool test case by identifier."""

        return self._test_cases.get(test_case_id)

    def test_cases(self) -> tuple[ToolTestCase, ...]:
        """Return all persisted tool test cases in insertion order."""

        return tuple(self._test_cases.values())

    @staticmethod
    def _reject_duplicate(
        *,
        artifact_name: str,
        artifact_id: UUID,
        existing: Mapping[UUID, object],
    ) -> None:
        """Reject replacement of an existing durable artifact."""

        if artifact_id in existing:
            raise ValueError(f"{artifact_name.capitalize()} {artifact_id} already exists.")


def require_tool_repository(
    repository: ToolRepository,
) -> ToolRepository:
    """Return a repository after static protocol validation."""

    return repository

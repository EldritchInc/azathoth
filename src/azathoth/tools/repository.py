"""Persistence contracts for durable tool artifacts."""

from typing import Protocol
from uuid import UUID

from azathoth.tools.definition import ToolDefinition
from azathoth.tools.document import ToolDocument
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.revision import ToolDocumentRevision
from azathoth.tools.testing import ToolTestCase


class ToolRepository(Protocol):
    """Persist and retrieve durable tool artifacts.

    Tool documents are revisioned: each `save_document` appends the next
    revision of the document's exact tool version and makes its artifacts
    current. The definition, implementation, and test case readers return
    current artifacts. The single-artifact savers never replace anything and
    are kept for artifacts assembled outside a document.
    """

    def save_definition(
        self,
        definition: ToolDefinition,
    ) -> None:
        """Persist one exact tool definition version."""

        ...

    def get_definition(
        self,
        tool_id: UUID,
        version: str,
    ) -> ToolDefinition | None:
        """Return one exact tool definition version."""

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

    def save_document(
        self,
        document: ToolDocument,
    ) -> ToolDocumentRevision:
        """Append one document as the next revision of its tool version.

        Raises:
            ValueError: An artifact ID in the document belongs to another
                tool, or an implementation ID to another version.
        """

        ...

    def latest_document_revision(
        self,
        tool_id: UUID,
        version: str,
    ) -> ToolDocumentRevision | None:
        """Return the latest revision of one exact tool version."""

        ...

    def document_revision(
        self,
        tool_id: UUID,
        version: str,
        number: int,
    ) -> ToolDocumentRevision | None:
        """Return one numbered revision of one exact tool version."""

        ...

    def document_revisions(
        self,
        tool_id: UUID,
    ) -> tuple[ToolDocumentRevision, ...]:
        """Return every revision of every version of one tool, in import order."""

        ...

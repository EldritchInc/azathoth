"""Deterministic in-memory persistence for durable tool artifacts."""

from collections.abc import Mapping
from uuid import UUID

from azathoth.tools.definition import ToolDefinition
from azathoth.tools.document import ToolDocument
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.repository import ToolRepository
from azathoth.tools.revision import (
    ToolDocumentRevision,
    document_artifact_conflict,
    retired_artifact_ids,
    unrevisioned_document,
)
from azathoth.tools.testing import ToolTestCase

ToolDefinitionReference = tuple[UUID, str]


class InMemoryToolRepository:
    """Store durable tool artifacts and revisioned tool documents in order."""

    def __init__(self) -> None:
        self._definitions: dict[
            ToolDefinitionReference,
            ToolDefinition,
        ] = {}
        self._implementations: dict[UUID, ToolImplementation] = {}
        self._test_cases: dict[UUID, ToolTestCase] = {}
        self._revisions: list[ToolDocumentRevision] = []

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

    def save_document(
        self,
        document: ToolDocument,
    ) -> ToolDocumentRevision:
        """Append one document as the next revision of its tool version.

        Versions of the tool saved artifact by artifact are first recorded
        as revision 1 of their own. Current artifacts then follow the new
        revision: retired implementations and test cases are removed, and
        the document's artifacts are added or replaced in place.

        Raises:
            ValueError: An artifact ID in the document belongs to another
                tool, or an implementation ID to another version.
        """

        definition = document.definition

        conflict = document_artifact_conflict(
            document,
            implementations=self._implementations.values(),
            test_cases=self._test_cases.values(),
        )

        if conflict is not None:
            raise ValueError(conflict)

        self._record_unrevisioned_versions(definition.id)

        previous = self.latest_document_revision(
            definition.id,
            definition.version,
        )

        revision = ToolDocumentRevision.create(
            document,
            number=previous.number + 1 if previous is not None else 1,
        )

        retired_implementations, retired_test_cases = retired_artifact_ids(
            previous=previous.document if previous is not None else None,
            current=document,
            other_versions=self._latest_documents_of_other_versions(definition),
        )

        self._revisions.append(revision)

        for implementation_id in retired_implementations:
            self._implementations.pop(implementation_id, None)

        for test_case_id in retired_test_cases:
            self._test_cases.pop(test_case_id, None)

        self._definitions[(definition.id, definition.version)] = definition

        for implementation in document.implementations:
            self._implementations[implementation.id] = implementation

        for test_case in document.test_cases:
            self._test_cases[test_case.id] = test_case

        return revision

    def latest_document_revision(
        self,
        tool_id: UUID,
        version: str,
    ) -> ToolDocumentRevision | None:
        """Return the latest revision of one exact tool version."""

        history = self._version_history(
            tool_id,
            version,
        )

        return history[-1] if history else None

    def document_revision(
        self,
        tool_id: UUID,
        version: str,
        number: int,
    ) -> ToolDocumentRevision | None:
        """Return one numbered revision of one exact tool version."""

        return next(
            (
                revision
                for revision in self._version_history(tool_id, version)
                if revision.number == number
            ),
            None,
        )

    def document_revisions(
        self,
        tool_id: UUID,
    ) -> tuple[ToolDocumentRevision, ...]:
        """Return every revision of every version of one tool, in import order."""

        return tuple(revision for revision in self._revisions if revision.tool_id == tool_id)

    def _version_history(
        self,
        tool_id: UUID,
        version: str,
    ) -> tuple[ToolDocumentRevision, ...]:
        """Return the revisions of one exact tool version, oldest first."""

        return tuple(
            revision
            for revision in self._revisions
            if revision.tool_id == tool_id and revision.tool_version == version
        )

    def _latest_documents_of_other_versions(
        self,
        definition: ToolDefinition,
    ) -> tuple[ToolDocument, ...]:
        """Return the latest document of every other revisioned version of a tool."""

        versions = dict.fromkeys(
            revision.tool_version
            for revision in self._revisions
            if revision.tool_id == definition.id and revision.tool_version != definition.version
        )

        documents: list[ToolDocument] = []

        for version in versions:
            latest = self.latest_document_revision(
                definition.id,
                version,
            )

            if latest is not None:
                documents.append(latest.document)

        return tuple(documents)

    def _record_unrevisioned_versions(
        self,
        tool_id: UUID,
    ) -> None:
        """Record every unrevisioned version of a tool as its revision 1."""

        for definition in self._definitions.values():
            if definition.id != tool_id:
                continue

            if self.latest_document_revision(definition.id, definition.version) is not None:
                continue

            self._revisions.append(
                ToolDocumentRevision.create(
                    unrevisioned_document(
                        definition,
                        implementations=self._implementations.values(),
                        test_cases=self._test_cases.values(),
                    ),
                    number=1,
                ).model_copy(
                    update={
                        "imported_at": None,
                    },
                )
            )

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

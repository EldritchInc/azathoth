"""Immutable revisions of portable tool documents."""

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from azathoth.revisions import (
    CONTENT_DIGEST_PATTERN,
    content_digest,
)
from azathoth.tools.definition import ToolDefinition
from azathoth.tools.document import ToolDocument
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.testing import ToolTestCase


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


class ToolDocumentRevision(BaseModel):
    """Record one import of a tool document under its exact tool version.

    The tool ID and version are the lineage; every import of a document for
    that version appends the next revision number and nothing is replaced.
    Re-importing an earlier document appends a revision whose digest matches
    the earlier one.

    Tool artifacts saved before revisions existed become revision 1 of their
    version with no import time, because it was never recorded.
    """

    model_config = ConfigDict(frozen=True)

    tool_id: UUID

    tool_version: str = Field(
        min_length=1,
    )

    number: int = Field(
        ge=1,
    )

    document: ToolDocument

    content_digest: str = Field(
        pattern=CONTENT_DIGEST_PATTERN,
    )

    imported_at: datetime | None = Field(
        default_factory=utc_now,
    )

    @model_validator(mode="after")
    def validate_document_identity(
        self,
    ) -> "ToolDocumentRevision":
        """Require the document to define the revision's exact tool version."""

        definition = self.document.definition

        if definition.id != self.tool_id or definition.version != self.tool_version:
            raise ValueError("Tool revision document must define its tool version.")

        return self

    @property
    def reference(
        self,
    ) -> str:
        """Return the revision's tool reference as `<tool ID>@<version>`."""

        return f"{self.tool_id}@{self.tool_version}"

    @classmethod
    def create(
        cls,
        document: ToolDocument,
        *,
        number: int,
        imported_at: datetime | None = None,
    ) -> "ToolDocumentRevision":
        """Return the revision recording one import of a tool document."""

        return cls(
            tool_id=document.definition.id,
            tool_version=document.definition.version,
            number=number,
            document=document,
            content_digest=content_digest(document),
            imported_at=imported_at if imported_at is not None else utc_now(),
        )


def earliest_identical_tool_revision(
    history: Iterable[ToolDocumentRevision],
    revision: ToolDocumentRevision,
) -> ToolDocumentRevision | None:
    """Return the earliest other revision of the same tool version with the same content."""

    matches = sorted(
        (
            candidate
            for candidate in history
            if candidate.tool_id == revision.tool_id
            and candidate.tool_version == revision.tool_version
            and candidate.number < revision.number
            and candidate.content_digest == revision.content_digest
        ),
        key=lambda candidate: candidate.number,
    )

    return matches[0] if matches else None


def unrevisioned_document(
    definition: ToolDefinition,
    *,
    implementations: Iterable[ToolImplementation],
    test_cases: Iterable[ToolTestCase],
) -> ToolDocument:
    """Assemble the document of one tool version saved before revisions existed.

    The document holds the version's implementations and every test case of
    the tool, since test cases belong to a tool rather than to one version.
    """

    return ToolDocument(
        definition=definition,
        implementations=tuple(
            implementation
            for implementation in implementations
            if implementation.tool_id == definition.id
            and implementation.tool_version == definition.version
        ),
        test_cases=tuple(
            test_case for test_case in test_cases if test_case.tool_id == definition.id
        ),
    )


def document_artifact_conflict(
    document: ToolDocument,
    *,
    definitions: Iterable[ToolDefinition],
    implementations: Iterable[ToolImplementation],
    test_cases: Iterable[ToolTestCase],
) -> str | None:
    """Return why a document's IDs clash with current artifacts, if they do.

    A tool ID already saved under another name clashes, in any version: a
    document never renames a tool, so a different tool that reuses an ID is
    rejected rather than recorded as a revision of the tool it collides
    with. An implementation ID already used by another tool, or by another
    version of the same tool, clashes. A test case ID already used by
    another tool clashes; test cases may be shared by the versions of one
    tool.
    """

    definition = document.definition

    for existing_definition in definitions:
        if existing_definition.id == definition.id and existing_definition.name != definition.name:
            return (
                f"Tool {definition.id} is named {existing_definition.name!r}; "
                f"a document cannot rename it to {definition.name!r}."
            )

    current_implementations = {
        implementation.id: implementation for implementation in implementations
    }

    for implementation in document.implementations:
        existing = current_implementations.get(implementation.id)

        if existing is None:
            continue

        if existing.tool_id != definition.id or existing.tool_version != definition.version:
            return (
                f"Tool implementation {implementation.id} belongs to tool "
                f"{existing.tool_id}@{existing.tool_version}."
            )

    current_test_cases = {test_case.id: test_case for test_case in test_cases}

    for test_case in document.test_cases:
        existing_test_case = current_test_cases.get(test_case.id)

        if existing_test_case is not None and existing_test_case.tool_id != definition.id:
            return f"Tool test case {test_case.id} belongs to tool {existing_test_case.tool_id}."

    return None


def retired_artifact_ids(
    *,
    previous: ToolDocument | None,
    current: ToolDocument,
    other_versions: Iterable[ToolDocument],
) -> tuple[frozenset[UUID], frozenset[UUID]]:
    """Return the implementation and test case IDs a new revision retires.

    An artifact of the previous revision is retired when the new revision no
    longer contains it. A test case still contained by the latest revision of
    another version of the same tool stays current.
    """

    if previous is None:
        return frozenset(), frozenset()

    kept_implementations = {implementation.id for implementation in current.implementations}

    kept_test_cases = {test_case.id for test_case in current.test_cases}

    for document in other_versions:
        kept_test_cases.update(test_case.id for test_case in document.test_cases)

    return (
        frozenset(
            implementation.id
            for implementation in previous.implementations
            if implementation.id not in kept_implementations
        ),
        frozenset(
            test_case.id for test_case in previous.test_cases if test_case.id not in kept_test_cases
        ),
    )

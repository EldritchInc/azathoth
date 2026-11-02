"""Durable tool artifacts, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import (
    Database,
    IntegrityError,
    Session,
    Table,
    require_text,
)
from azathoth.persistence.dialect import identifier
from azathoth.tools.definition import ToolDefinition
from azathoth.tools.document import ToolDocument
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.revision import (
    ToolDocumentRevision,
    document_artifact_conflict,
    retired_artifact_ids,
    unrevisioned_document,
)
from azathoth.tools.testing import ToolTestCase

TOOL_DOCUMENT_REVISIONS = "tool_document_revisions"

TOOL_DEFINITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS tool_definitions (
    sequence {sequence},
    artifact_id TEXT NOT NULL,
    artifact_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE (
        artifact_id,
        artifact_version
    )
)
"""
"""The statement that creates the table of current tool definitions."""

TOOL_TABLES = (
    Table(
        name="tool_definitions",
        statements=(TOOL_DEFINITIONS_TABLE,),
    ),
    Table(
        name="tool_implementations",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS tool_implementations (
                sequence {sequence},
                artifact_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            )
            """,
        ),
    ),
    Table(
        name="tool_test_cases",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS tool_test_cases (
                sequence {sequence},
                artifact_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            )
            """,
        ),
    ),
    Table(
        name=TOOL_DOCUMENT_REVISIONS,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS tool_document_revisions (
                sequence {sequence},
                tool_id TEXT NOT NULL,
                tool_version TEXT NOT NULL,
                number INTEGER NOT NULL,
                content_digest TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (
                    tool_id,
                    tool_version,
                    number
                )
            )
            """,
        ),
    ),
)
"""The tables tool artifacts and tool document revisions are kept in."""


class SqlToolRepository:
    """Persist durable tool artifacts in a database.

    Tool document revisions live in `tool_document_revisions`. The definition,
    implementation, and test case tables hold the current artifacts.
    """

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(TOOL_TABLES)

    def save_definition(
        self,
        definition: ToolDefinition,
    ) -> None:
        """Persist one exact tool definition version without replacement.

        Raises:
            ValueError: That exact version already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
                    """
                    INSERT INTO tool_definitions (
                        artifact_id,
                        artifact_version,
                        payload
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        str(definition.id),
                        definition.version,
                        definition.model_dump_json(),
                    ),
                )
        except IntegrityError as exc:
            raise ValueError(
                f"Tool definition {definition.id}@{definition.version} already exists."
            ) from exc

    def get_definition(
        self,
        tool_id: UUID,
        version: str,
    ) -> ToolDefinition | None:
        """Return one exact tool definition version."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM tool_definitions
                WHERE artifact_id = ?
                  AND artifact_version = ?
                """,
                (
                    str(tool_id),
                    version,
                ),
            )

        if row is None:
            return None

        return ToolDefinition.model_validate_json(
            require_text(row[0], f"Persisted tool definition {tool_id}@{version} was not text.")
        )

    def definitions(self) -> tuple[ToolDefinition, ...]:
        """Return all persisted tool definitions in insertion order."""

        with self._database.transaction() as session:
            return tuple(
                ToolDefinition.model_validate_json(payload)
                for payload in payloads(session, "tool_definitions")
            )

    def save_implementation(
        self,
        implementation: ToolImplementation,
    ) -> None:
        """Persist one tool implementation without replacing existing data."""

        self._insert(
            table="tool_implementations",
            artifact_name="tool implementation",
            artifact_id=implementation.id,
            payload=implementation.model_dump_json(),
        )

    def get_implementation(
        self,
        implementation_id: UUID,
    ) -> ToolImplementation | None:
        """Return a tool implementation by identifier."""

        payload = self._get(
            table="tool_implementations",
            artifact_id=implementation_id,
        )

        if payload is None:
            return None

        return ToolImplementation.model_validate_json(payload)

    def implementations(self) -> tuple[ToolImplementation, ...]:
        """Return all persisted tool implementations in insertion order."""

        with self._database.transaction() as session:
            return implementations(session)

    def save_test_case(
        self,
        test_case: ToolTestCase,
    ) -> None:
        """Persist one tool test case without replacing existing data."""

        self._insert(
            table="tool_test_cases",
            artifact_name="tool test case",
            artifact_id=test_case.id,
            payload=test_case.model_dump_json(),
        )

    def get_test_case(
        self,
        test_case_id: UUID,
    ) -> ToolTestCase | None:
        """Return a tool test case by identifier."""

        payload = self._get(
            table="tool_test_cases",
            artifact_id=test_case_id,
        )

        if payload is None:
            return None

        return ToolTestCase.model_validate_json(payload)

    def test_cases(self) -> tuple[ToolTestCase, ...]:
        """Return all persisted tool test cases in insertion order."""

        with self._database.transaction() as session:
            return test_cases(session)

    def save_document(
        self,
        document: ToolDocument,
    ) -> ToolDocumentRevision:
        """Append one document as the next revision of its tool version.

        The revision and the change to current artifacts are written in one
        transaction holding the revision table's write lock, so concurrent
        imports never receive the same number. Versions of the tool saved
        artifact by artifact are first recorded as revision 1 of their own.
        Retired implementations and test cases are removed, and the
        document's artifacts are added or replaced in place.

        Raises:
            ValueError: The tool ID is saved under another name, an artifact
                ID in the document belongs to another tool, or an
                implementation ID to another version.
        """

        definition = document.definition

        with self._database.transaction(lock=TOOL_DOCUMENT_REVISIONS) as session:
            conflict = document_artifact_conflict(
                document,
                definitions=definitions(session),
                implementations=implementations(session),
                test_cases=test_cases(session),
            )

            if conflict is not None:
                raise ValueError(conflict)

            record_unrevisioned_versions(
                session,
                tool_id=definition.id,
            )

            previous = latest_revision(
                session,
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
                other_versions=_latest_documents_of_other_versions(
                    session,
                    definition,
                ),
            )

            insert_revision(
                session,
                revision,
            )

            for implementation_id in retired_implementations:
                session.execute(
                    "DELETE FROM tool_implementations WHERE artifact_id = ?",
                    (str(implementation_id),),
                )

            for test_case_id in retired_test_cases:
                session.execute(
                    "DELETE FROM tool_test_cases WHERE artifact_id = ?",
                    (str(test_case_id),),
                )

            session.execute(
                """
                INSERT INTO tool_definitions (
                    artifact_id,
                    artifact_version,
                    payload
                )
                VALUES (?, ?, ?)
                ON CONFLICT (artifact_id, artifact_version)
                DO UPDATE SET payload = excluded.payload
                """,
                (
                    str(definition.id),
                    definition.version,
                    definition.model_dump_json(),
                ),
            )

            for implementation in document.implementations:
                _upsert(
                    session,
                    table="tool_implementations",
                    artifact_id=implementation.id,
                    payload=implementation.model_dump_json(),
                )

            for test_case in document.test_cases:
                _upsert(
                    session,
                    table="tool_test_cases",
                    artifact_id=test_case.id,
                    payload=test_case.model_dump_json(),
                )

        return revision

    def latest_document_revision(
        self,
        tool_id: UUID,
        version: str,
    ) -> ToolDocumentRevision | None:
        """Return the latest revision of one exact tool version."""

        with self._database.transaction() as session:
            return latest_revision(
                session,
                tool_id,
                version,
            )

    def document_revision(
        self,
        tool_id: UUID,
        version: str,
        number: int,
    ) -> ToolDocumentRevision | None:
        """Return one numbered revision of one exact tool version."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM tool_document_revisions
                WHERE tool_id = ? AND tool_version = ? AND number = ?
                """,
                (
                    str(tool_id),
                    version,
                    number,
                ),
            )

        if row is None:
            return None

        return _deserialize_revision(row[0])

    def document_revisions(
        self,
        tool_id: UUID,
    ) -> tuple[ToolDocumentRevision, ...]:
        """Return every revision of every version of one tool, in import order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM tool_document_revisions
                WHERE tool_id = ?
                ORDER BY sequence
                """,
                (str(tool_id),),
            )

        return tuple(_deserialize_revision(row[0]) for row in rows)

    def _insert(
        self,
        *,
        table: str,
        artifact_name: str,
        artifact_id: UUID,
        payload: str,
    ) -> None:
        """Insert one append-only UUID-identified artifact.

        Raises:
            ValueError: An artifact with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
                    f"""
                    INSERT INTO {identifier(table)} (
                        artifact_id,
                        payload
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(artifact_id),
                        payload,
                    ),
                )
        except IntegrityError as exc:
            raise ValueError(f"{artifact_name.capitalize()} {artifact_id} already exists.") from exc

    def _get(
        self,
        *,
        table: str,
        artifact_id: UUID,
    ) -> str | None:
        """Return one serialized UUID-identified artifact."""

        with self._database.transaction() as session:
            row = session.fetchone(
                f"""
                SELECT payload
                FROM {identifier(table)}
                WHERE artifact_id = ?
                """,
                (str(artifact_id),),
            )

        if row is None:
            return None

        return require_text(row[0], f"Persisted payload for {artifact_id} was not text.")


def payloads(
    session: Session,
    table: str,
) -> tuple[str, ...]:
    """Return every serialized artifact of one table in insertion order."""

    rows = session.fetchall(
        f"""
        SELECT payload
        FROM {identifier(table)}
        ORDER BY sequence
        """
    )

    return tuple(
        require_text(row[0], f"Persisted payload in {table} was not text.") for row in rows
    )


def definitions(
    session: Session,
) -> tuple[ToolDefinition, ...]:
    """Return every saved definition, of every version."""

    return tuple(
        ToolDefinition.model_validate_json(payload)
        for payload in payloads(session, "tool_definitions")
    )


def implementations(
    session: Session,
) -> tuple[ToolImplementation, ...]:
    """Return every current implementation."""

    return tuple(
        ToolImplementation.model_validate_json(payload)
        for payload in payloads(session, "tool_implementations")
    )


def test_cases(
    session: Session,
) -> tuple[ToolTestCase, ...]:
    """Return every current test case."""

    return tuple(
        ToolTestCase.model_validate_json(payload)
        for payload in payloads(session, "tool_test_cases")
    )


def _upsert(
    session: Session,
    *,
    table: str,
    artifact_id: UUID,
    payload: str,
) -> None:
    """Insert one current artifact, or replace its payload in place."""

    session.execute(
        f"""
        INSERT INTO {identifier(table)} (
            artifact_id,
            payload
        )
        VALUES (?, ?)
        ON CONFLICT (artifact_id)
        DO UPDATE SET payload = excluded.payload
        """,
        (
            str(artifact_id),
            payload,
        ),
    )


def insert_revision(
    session: Session,
    revision: ToolDocumentRevision,
) -> None:
    """Insert one tool document revision row."""

    session.execute(
        """
        INSERT INTO tool_document_revisions (
            tool_id,
            tool_version,
            number,
            content_digest,
            payload
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(revision.tool_id),
            revision.tool_version,
            revision.number,
            revision.content_digest,
            revision.model_dump_json(),
        ),
    )


def latest_revision(
    session: Session,
    tool_id: UUID,
    version: str,
) -> ToolDocumentRevision | None:
    """Return the latest revision of one exact tool version."""

    row = session.fetchone(
        """
        SELECT payload
        FROM tool_document_revisions
        WHERE tool_id = ? AND tool_version = ?
        ORDER BY number DESC
        LIMIT 1
        """,
        (
            str(tool_id),
            version,
        ),
    )

    if row is None:
        return None

    return _deserialize_revision(row[0])


def _latest_documents_of_other_versions(
    session: Session,
    definition: ToolDefinition,
) -> tuple[ToolDocument, ...]:
    """Return the latest document of every other revisioned version of a tool."""

    rows = session.fetchall(
        """
        SELECT DISTINCT tool_version
        FROM tool_document_revisions
        WHERE tool_id = ? AND tool_version != ?
        """,
        (
            str(definition.id),
            definition.version,
        ),
    )

    documents: list[ToolDocument] = []

    for row in rows:
        latest = latest_revision(
            session,
            definition.id,
            str(row[0]),
        )

        if latest is not None:
            documents.append(latest.document)

    return tuple(documents)


def record_unrevisioned_versions(
    session: Session,
    *,
    tool_id: UUID | None,
) -> None:
    """Record unrevisioned tool versions as revision 1, without an import time.

    With a tool ID, only that tool's versions are considered; otherwise every
    tool's are. Versions that already have revisions are left alone, so this
    is safe to run at any time.
    """

    definitions = tuple(
        ToolDefinition.model_validate_json(payload)
        for payload in payloads(session, "tool_definitions")
    )

    pending = tuple(
        definition
        for definition in definitions
        if (tool_id is None or definition.id == tool_id)
        and latest_revision(session, definition.id, definition.version) is None
    )

    if not pending:
        return

    current_implementations = implementations(session)
    current_test_cases = test_cases(session)

    for definition in pending:
        insert_revision(
            session,
            ToolDocumentRevision.create(
                unrevisioned_document(
                    definition,
                    implementations=current_implementations,
                    test_cases=current_test_cases,
                ),
                number=1,
            ).model_copy(
                update={
                    "imported_at": None,
                },
            ),
        )


def _deserialize_revision(
    payload: object,
) -> ToolDocumentRevision:
    """Reconstruct one persisted tool document revision.

    Raises:
        TypeError: The persisted payload is not text.
    """

    return ToolDocumentRevision.model_validate_json(
        require_text(payload, "Persisted tool revision payload was not text.")
    )


__all__ = [
    "TOOL_DEFINITIONS_TABLE",
    "TOOL_DOCUMENT_REVISIONS",
    "TOOL_TABLES",
    "SqlToolRepository",
    "definitions",
    "implementations",
    "insert_revision",
    "latest_revision",
    "payloads",
    "record_unrevisioned_versions",
    "test_cases",
]

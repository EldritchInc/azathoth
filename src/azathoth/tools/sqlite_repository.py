"""SQLite persistence for durable tool artifacts."""

import sqlite3
from pathlib import Path
from uuid import UUID

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


class SQLiteToolRepository:
    """Persist durable tool artifacts in a SQLite database.

    Tool document revisions live in `tool_document_revisions`. The definition,
    implementation, and test case tables hold the current artifacts. Opening a
    database whose tool versions predate revisions records each such version
    as revision 1, without an import time.
    """

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save_definition(
        self,
        definition: ToolDefinition,
    ) -> None:
        """Persist one exact tool definition version without replacement."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
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

                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"Tool definition {definition.id}@{definition.version} already exists."
                ) from exc
        finally:
            connection.close()

    def get_definition(
        self,
        tool_id: UUID,
        version: str,
    ) -> ToolDefinition | None:
        """Return one exact tool definition version."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
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
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        payload = row[0]

        if not isinstance(payload, str):
            raise TypeError(f"Persisted tool definition {tool_id}@{version} was not text.")

        return ToolDefinition.model_validate_json(payload)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        """Return all persisted tool definitions in insertion order."""

        return tuple(
            ToolDefinition.model_validate_json(payload) for payload in self._all("tool_definitions")
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

        return tuple(
            ToolImplementation.model_validate_json(payload)
            for payload in self._all("tool_implementations")
        )

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

        return tuple(
            ToolTestCase.model_validate_json(payload) for payload in self._all("tool_test_cases")
        )

    def save_document(
        self,
        document: ToolDocument,
    ) -> ToolDocumentRevision:
        """Append one document as the next revision of its tool version.

        The revision and the change to current artifacts are written in one
        immediate transaction. Versions of the tool saved artifact by artifact
        are first recorded as revision 1 of their own. Retired implementations
        and test cases are removed, and the document's artifacts are added or
        replaced in place.

        Raises:
            ValueError: An artifact ID in the document belongs to another
                tool, or an implementation ID to another version.
        """

        definition = document.definition

        connection = sqlite3.connect(
            self._database,
            isolation_level=None,
        )

        try:
            connection.execute("BEGIN IMMEDIATE")

            try:
                implementations = _implementations(connection)
                test_cases = _test_cases(connection)

                conflict = document_artifact_conflict(
                    document,
                    implementations=implementations,
                    test_cases=test_cases,
                )

                if conflict is not None:
                    raise ValueError(conflict)

                _record_unrevisioned_versions(
                    connection,
                    tool_id=definition.id,
                )

                previous = _latest_revision(
                    connection,
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
                        connection,
                        definition,
                    ),
                )

                _insert_revision(
                    connection,
                    revision,
                )

                for implementation_id in retired_implementations:
                    connection.execute(
                        "DELETE FROM tool_implementations WHERE artifact_id = ?",
                        (str(implementation_id),),
                    )

                for test_case_id in retired_test_cases:
                    connection.execute(
                        "DELETE FROM tool_test_cases WHERE artifact_id = ?",
                        (str(test_case_id),),
                    )

                connection.execute(
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
                        connection,
                        table="tool_implementations",
                        artifact_id=implementation.id,
                        payload=implementation.model_dump_json(),
                    )

                for test_case in document.test_cases:
                    _upsert(
                        connection,
                        table="tool_test_cases",
                        artifact_id=test_case.id,
                        payload=test_case.model_dump_json(),
                    )

                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()

        return revision

    def latest_document_revision(
        self,
        tool_id: UUID,
        version: str,
    ) -> ToolDocumentRevision | None:
        """Return the latest revision of one exact tool version."""

        connection = sqlite3.connect(self._database)

        try:
            return _latest_revision(
                connection,
                tool_id,
                version,
            )
        finally:
            connection.close()

    def document_revision(
        self,
        tool_id: UUID,
        version: str,
        number: int,
    ) -> ToolDocumentRevision | None:
        """Return one numbered revision of one exact tool version."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
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
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return _deserialize_revision(row[0])

    def document_revisions(
        self,
        tool_id: UUID,
    ) -> tuple[ToolDocumentRevision, ...]:
        """Return every revision of every version of one tool, in import order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM tool_document_revisions
                WHERE tool_id = ?
                ORDER BY sequence
                """,
                (str(tool_id),),
            ).fetchall()
        finally:
            connection.close()

        return tuple(_deserialize_revision(row[0]) for row in rows)

    def _initialize(self) -> None:
        """Create repository tables and migrate definition identity."""

        connection = sqlite3.connect(self._database)

        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tool_definitions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT NOT NULL,
                    artifact_version TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE (
                        artifact_id,
                        artifact_version
                    )
                );

                CREATE TABLE IF NOT EXISTS tool_implementations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tool_test_cases (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tool_document_revisions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
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
                );
                """
            )

            self._migrate_tool_definitions(
                connection,
            )

            _record_unrevisioned_versions(
                connection,
                tool_id=None,
            )

            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _migrate_tool_definitions(
        connection: sqlite3.Connection,
    ) -> None:
        """Migrate UUID-only tool definitions to versioned references."""

        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(tool_definitions)").fetchall()
        }

        if "artifact_version" in columns:
            return

        rows = connection.execute(
            """
            SELECT payload
            FROM tool_definitions
            ORDER BY sequence
            """
        ).fetchall()

        definitions: list[ToolDefinition] = []

        for row in rows:
            payload = row[0]

            if not isinstance(payload, str):
                raise TypeError("Persisted tool definition payload was not text.")

            definitions.append(ToolDefinition.model_validate_json(payload))

        connection.execute("ALTER TABLE tool_definitions RENAME TO tool_definitions_legacy")

        connection.execute(
            """
            CREATE TABLE tool_definitions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id TEXT NOT NULL,
                artifact_version TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (
                    artifact_id,
                    artifact_version
                )
            )
            """
        )

        for definition in definitions:
            connection.execute(
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

        connection.execute("DROP TABLE tool_definitions_legacy")

    def _insert(
        self,
        *,
        table: str,
        artifact_name: str,
        artifact_id: UUID,
        payload: str,
    ) -> None:
        """Insert one append-only UUID-identified artifact."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    f"""
                    INSERT INTO {table} (
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

                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"{artifact_name.capitalize()} {artifact_id} already exists."
                ) from exc
        finally:
            connection.close()

    def _get(
        self,
        *,
        table: str,
        artifact_id: UUID,
    ) -> str | None:
        """Return one serialized UUID-identified artifact."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                f"""
                SELECT payload
                FROM {table}
                WHERE artifact_id = ?
                """,
                (str(artifact_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        payload = row[0]

        if not isinstance(payload, str):
            raise TypeError(f"Persisted payload for {artifact_id} was not text.")

        return payload

    def _all(
        self,
        table: str,
    ) -> tuple[str, ...]:
        """Return serialized artifacts in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                f"""
                SELECT payload
                FROM {table}
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        payloads: list[str] = []

        for row in rows:
            payload = row[0]

            if not isinstance(payload, str):
                raise TypeError(f"Persisted payload in {table} was not text.")

            payloads.append(payload)

        return tuple(payloads)


def _payloads(
    connection: sqlite3.Connection,
    table: str,
) -> tuple[str, ...]:
    """Return every serialized artifact of one table in insertion order."""

    rows = connection.execute(
        f"""
        SELECT payload
        FROM {table}
        ORDER BY sequence
        """
    ).fetchall()

    payloads: list[str] = []

    for row in rows:
        payload = row[0]

        if not isinstance(payload, str):
            raise TypeError(f"Persisted payload in {table} was not text.")

        payloads.append(payload)

    return tuple(payloads)


def _implementations(
    connection: sqlite3.Connection,
) -> tuple[ToolImplementation, ...]:
    """Return every current implementation."""

    return tuple(
        ToolImplementation.model_validate_json(payload)
        for payload in _payloads(connection, "tool_implementations")
    )


def _test_cases(
    connection: sqlite3.Connection,
) -> tuple[ToolTestCase, ...]:
    """Return every current test case."""

    return tuple(
        ToolTestCase.model_validate_json(payload)
        for payload in _payloads(connection, "tool_test_cases")
    )


def _upsert(
    connection: sqlite3.Connection,
    *,
    table: str,
    artifact_id: UUID,
    payload: str,
) -> None:
    """Insert one current artifact, or replace its payload in place."""

    connection.execute(
        f"""
        INSERT INTO {table} (
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


def _insert_revision(
    connection: sqlite3.Connection,
    revision: ToolDocumentRevision,
) -> None:
    """Insert one tool document revision row."""

    connection.execute(
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


def _latest_revision(
    connection: sqlite3.Connection,
    tool_id: UUID,
    version: str,
) -> ToolDocumentRevision | None:
    """Return the latest revision of one exact tool version."""

    row = connection.execute(
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
    ).fetchone()

    if row is None:
        return None

    return _deserialize_revision(row[0])


def _latest_documents_of_other_versions(
    connection: sqlite3.Connection,
    definition: ToolDefinition,
) -> tuple[ToolDocument, ...]:
    """Return the latest document of every other revisioned version of a tool."""

    rows = connection.execute(
        """
        SELECT DISTINCT tool_version
        FROM tool_document_revisions
        WHERE tool_id = ? AND tool_version != ?
        """,
        (
            str(definition.id),
            definition.version,
        ),
    ).fetchall()

    documents: list[ToolDocument] = []

    for row in rows:
        latest = _latest_revision(
            connection,
            definition.id,
            str(row[0]),
        )

        if latest is not None:
            documents.append(latest.document)

    return tuple(documents)


def _record_unrevisioned_versions(
    connection: sqlite3.Connection,
    *,
    tool_id: UUID | None,
) -> None:
    """Record unrevisioned tool versions as revision 1, without an import time.

    With a tool ID, only that tool's versions are considered; otherwise every
    tool's are. Versions that already have revisions are left alone, so this
    is safe to run whenever a repository opens.
    """

    definitions = tuple(
        ToolDefinition.model_validate_json(payload)
        for payload in _payloads(connection, "tool_definitions")
    )

    pending = tuple(
        definition
        for definition in definitions
        if (tool_id is None or definition.id == tool_id)
        and _latest_revision(connection, definition.id, definition.version) is None
    )

    if not pending:
        return

    implementations = _implementations(connection)
    test_cases = _test_cases(connection)

    for definition in pending:
        _insert_revision(
            connection,
            ToolDocumentRevision.create(
                unrevisioned_document(
                    definition,
                    implementations=implementations,
                    test_cases=test_cases,
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

    if not isinstance(payload, str):
        raise TypeError("Persisted tool revision payload was not text.")

    return ToolDocumentRevision.model_validate_json(payload)

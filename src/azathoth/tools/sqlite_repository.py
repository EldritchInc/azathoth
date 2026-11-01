"""SQLite persistence for durable tool artifacts."""

from pathlib import Path

from azathoth.persistence import Session, SQLiteDatabase, require_text
from azathoth.tools.definition import ToolDefinition
from azathoth.tools.sql_repository import (
    TOOL_DEFINITIONS_TABLE,
    SqlToolRepository,
    record_unrevisioned_versions,
)


class SQLiteToolRepository(SqlToolRepository):
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
        sqlite = SQLiteDatabase(database)

        super().__init__(sqlite)

        with sqlite.transaction() as session:
            _migrate_tool_definitions(session)

            record_unrevisioned_versions(
                session,
                tool_id=None,
            )


def _migrate_tool_definitions(
    session: Session,
) -> None:
    """Migrate UUID-only tool definitions to versioned references."""

    columns = {row[1] for row in session.fetchall("PRAGMA table_info(tool_definitions)")}

    if "artifact_version" in columns:
        return

    rows = session.fetchall(
        """
        SELECT payload
        FROM tool_definitions
        ORDER BY sequence
        """
    )

    definitions = [
        ToolDefinition.model_validate_json(
            require_text(row[0], "Persisted tool definition payload was not text.")
        )
        for row in rows
    ]

    session.execute("ALTER TABLE tool_definitions RENAME TO tool_definitions_legacy")
    session.execute(TOOL_DEFINITIONS_TABLE)

    for definition in definitions:
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

    session.execute("DROP TABLE tool_definitions_legacy")

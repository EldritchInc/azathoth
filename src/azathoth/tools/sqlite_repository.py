"""SQLite persistence for durable tool artifacts."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.tools.definition import ToolDefinition
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.testing import ToolTestCase


class SQLiteToolRepository:
    """Persist durable tool artifacts in a SQLite database."""

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
                """
            )

            self._migrate_tool_definitions(
                connection,
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

"""SQLite persistence for immutable workflow production revisions."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.production import WorkflowProductionRevision


class SQLiteWorkflowProductionRevisionRepository:
    """Persist immutable workflow production revisions in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)

        self._initialize()

    def save(
        self,
        revision: WorkflowProductionRevision,
    ) -> None:
        """Persist one production revision without replacing history."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_production_revisions (
                        revision_id,
                        workflow_id,
                        payload
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        str(revision.id),
                        str(revision.workflow_id),
                        revision.model_dump_json(),
                    ),
                )

                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"Workflow production revision {revision.id} already exists."
                ) from exc
        finally:
            connection.close()

    def get(
        self,
        revision_id: UUID,
    ) -> WorkflowProductionRevision | None:
        """Return one production revision by identifier."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_production_revisions
                WHERE revision_id = ?
                """,
                (str(revision_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(
            row[0],
        )

    def revisions(
        self,
    ) -> tuple[WorkflowProductionRevision, ...]:
        """Return all production revisions in insertion order."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_production_revisions
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(
            self._deserialize_payload(
                row[0],
            )
            for row in rows
        )

    def revisions_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowProductionRevision, ...]:
        """Return production revisions for one workflow in insertion order."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_production_revisions
                WHERE workflow_id = ?
                ORDER BY sequence
                """,
                (str(workflow_id),),
            ).fetchall()
        finally:
            connection.close()

        return tuple(
            self._deserialize_payload(
                row[0],
            )
            for row in rows
        )

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> WorkflowProductionRevision:
        """Reconstruct one persisted workflow production revision."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted workflow production revision payload was not text.")

        return WorkflowProductionRevision.model_validate_json(
            payload,
        )

    def _initialize(
        self,
    ) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_production_revisions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision_id TEXT NOT NULL UNIQUE,
                    workflow_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_production_revisions_workflow_id_sequence
                ON workflow_production_revisions (
                    workflow_id,
                    sequence
                )
                """
            )

            connection.commit()
        finally:
            connection.close()

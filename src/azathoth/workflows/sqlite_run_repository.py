"""SQLite persistence for durable workflow run evidence."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.execution import WorkflowRun


class SQLiteWorkflowRunRepository:
    """Persist immutable workflow run evidence in a SQLite database."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        run: WorkflowRun,
    ) -> None:
        """Persist one workflow run without replacing existing evidence."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_runs (
                        run_id,
                        workflow_id,
                        payload
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        str(run.id),
                        str(run.workflow.id),
                        run.model_dump_json(),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Workflow run {run.id} already exists.") from exc
        finally:
            connection.close()

    def get(
        self,
        run_id: UUID,
    ) -> WorkflowRun | None:
        """Return a workflow run by identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_runs
                WHERE run_id = ?
                """,
                (str(run_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        payload = row[0]

        if not isinstance(payload, str):
            raise TypeError(f"Persisted workflow run payload for {run_id} was not text.")

        return WorkflowRun.model_validate_json(payload)

    def runs(
        self,
    ) -> tuple[WorkflowRun, ...]:
        """Return all persisted workflow runs in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_runs
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

    def runs_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowRun, ...]:
        """Return persisted runs for one workflow in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_runs
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
    ) -> WorkflowRun:
        """Reconstruct one persisted workflow run payload."""

        if not isinstance(payload, str):
            raise TypeError("Persisted workflow run payload was not text.")

        return WorkflowRun.model_validate_json(payload)

    def _initialize(self) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    workflow_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_runs_workflow_id_sequence
                ON workflow_runs (
                    workflow_id,
                    sequence
                )
                """
            )

            connection.commit()
        finally:
            connection.close()

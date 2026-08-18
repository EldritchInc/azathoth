"""SQLite persistence for immutable workflow run feedback."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.feedback import WorkflowRunFeedback


class SQLiteWorkflowRunFeedbackRepository:
    """Persist workflow run feedback in a SQLite database."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        feedback: WorkflowRunFeedback,
    ) -> None:
        """Persist feedback without replacing existing evidence."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_run_feedback (
                        feedback_id,
                        run_id,
                        disposition,
                        payload
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(feedback.id),
                        str(feedback.run_id),
                        feedback.disposition.value,
                        feedback.model_dump_json(),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Workflow run feedback {feedback.id} already exists.") from exc
        finally:
            connection.close()

    def get(
        self,
        feedback_id: UUID,
    ) -> WorkflowRunFeedback | None:
        """Return workflow run feedback by identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_run_feedback
                WHERE feedback_id = ?
                """,
                (str(feedback_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def feedback(
        self,
    ) -> tuple[WorkflowRunFeedback, ...]:
        """Return all feedback records in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_run_feedback
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def feedback_for_run(
        self,
        run_id: UUID,
    ) -> tuple[WorkflowRunFeedback, ...]:
        """Return feedback for one workflow run in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_run_feedback
                WHERE run_id = ?
                ORDER BY sequence
                """,
                (str(run_id),),
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> WorkflowRunFeedback:
        """Reconstruct one persisted feedback record."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted workflow run feedback payload was not text.")

        return WorkflowRunFeedback.model_validate_json(payload)

    def _initialize(self) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_run_feedback (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    feedback_id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_run_feedback_run_id_sequence
                ON workflow_run_feedback (
                    run_id,
                    sequence
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_run_feedback_disposition_sequence
                ON workflow_run_feedback (
                    disposition,
                    sequence
                )
                """
            )

            connection.commit()
        finally:
            connection.close()

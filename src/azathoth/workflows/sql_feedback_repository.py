"""Immutable workflow run feedback, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, IntegrityError, Table
from azathoth.workflows.feedback import WorkflowRunFeedback

WORKFLOW_RUN_FEEDBACK_TABLES = (
    Table(
        name="workflow_run_feedback",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_run_feedback (
                sequence {sequence},
                feedback_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL,
                disposition TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_run_feedback_run_id_sequence
            ON workflow_run_feedback (
                run_id,
                sequence
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_run_feedback_disposition_sequence
            ON workflow_run_feedback (
                disposition,
                sequence
            )
            """,
        ),
    ),
)
"""The tables workflow run feedback is kept in."""


class SqlWorkflowRunFeedbackRepository:
    """Persist workflow run feedback in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(WORKFLOW_RUN_FEEDBACK_TABLES)

    def save(
        self,
        feedback: WorkflowRunFeedback,
    ) -> None:
        """Persist feedback without replacing existing evidence.

        Raises:
            ValueError: Feedback with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
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
        except IntegrityError as exc:
            raise ValueError(f"Workflow run feedback {feedback.id} already exists.") from exc

    def get(
        self,
        feedback_id: UUID,
    ) -> WorkflowRunFeedback | None:
        """Return workflow run feedback by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM workflow_run_feedback
                WHERE feedback_id = ?
                """,
                (str(feedback_id),),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def feedback(
        self,
    ) -> tuple[WorkflowRunFeedback, ...]:
        """Return all feedback records in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_run_feedback
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def feedback_for_run(
        self,
        run_id: UUID,
    ) -> tuple[WorkflowRunFeedback, ...]:
        """Return feedback for one workflow run in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_run_feedback
                WHERE run_id = ?
                ORDER BY sequence
                """,
                (str(run_id),),
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> WorkflowRunFeedback:
        """Reconstruct one persisted feedback record."""

        if not isinstance(payload, str):
            raise TypeError("Persisted workflow run feedback payload was not text.")

        return WorkflowRunFeedback.model_validate_json(payload)


__all__ = [
    "WORKFLOW_RUN_FEEDBACK_TABLES",
    "SqlWorkflowRunFeedbackRepository",
]

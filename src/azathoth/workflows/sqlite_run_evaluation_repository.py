"""SQLite persistence for immutable workflow run evaluations."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.run_evaluation import WorkflowRunEvaluation


class SQLiteWorkflowRunEvaluationRepository:
    """Persist workflow run evaluations in a SQLite database."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        run_evaluation: WorkflowRunEvaluation,
    ) -> None:
        """Persist one evaluation without replacing existing evidence."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_run_evaluations (
                        evaluation_id,
                        run_id,
                        evaluator_name,
                        payload
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(run_evaluation.id),
                        str(run_evaluation.run_id),
                        run_evaluation.evaluation.evaluator_name,
                        run_evaluation.model_dump_json(),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"Workflow run evaluation {run_evaluation.id} already exists."
                ) from exc
        finally:
            connection.close()

    def get(
        self,
        evaluation_id: UUID,
    ) -> WorkflowRunEvaluation | None:
        """Return one run evaluation by evaluation identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_run_evaluations
                WHERE evaluation_id = ?
                """,
                (str(evaluation_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def evaluations(
        self,
    ) -> tuple[WorkflowRunEvaluation, ...]:
        """Return all run evaluations in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_run_evaluations
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def evaluations_for_run(
        self,
        run_id: UUID,
    ) -> tuple[WorkflowRunEvaluation, ...]:
        """Return evaluations for one workflow run in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_run_evaluations
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
    ) -> WorkflowRunEvaluation:
        """Reconstruct one persisted workflow run evaluation."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted workflow run evaluation payload was not text.")

        return WorkflowRunEvaluation.model_validate_json(payload)

    def _initialize(self) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_run_evaluations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluation_id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL,
                    evaluator_name TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_run_evaluations_run_id_sequence
                ON workflow_run_evaluations (
                    run_id,
                    sequence
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    workflow_run_evaluations_evaluator_sequence
                ON workflow_run_evaluations (
                    evaluator_name,
                    sequence
                )
                """
            )

            connection.commit()
        finally:
            connection.close()

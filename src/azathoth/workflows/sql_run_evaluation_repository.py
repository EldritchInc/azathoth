"""Immutable workflow run evaluations, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, IntegrityError, Table
from azathoth.workflows.run_evaluation import WorkflowRunEvaluation

WORKFLOW_RUN_EVALUATION_TABLES = (
    Table(
        name="workflow_run_evaluations",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_run_evaluations (
                sequence {sequence},
                evaluation_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL,
                evaluator_name TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_run_evaluations_run_id_sequence
            ON workflow_run_evaluations (
                run_id,
                sequence
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_run_evaluations_evaluator_sequence
            ON workflow_run_evaluations (
                evaluator_name,
                sequence
            )
            """,
        ),
    ),
)
"""The tables workflow run evaluations are kept in."""


class SqlWorkflowRunEvaluationRepository:
    """Persist workflow run evaluations in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(WORKFLOW_RUN_EVALUATION_TABLES)

    def save(
        self,
        run_evaluation: WorkflowRunEvaluation,
    ) -> None:
        """Persist one evaluation without replacing existing evidence.

        Raises:
            ValueError: An evaluation with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
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
        except IntegrityError as exc:
            raise ValueError(
                f"Workflow run evaluation {run_evaluation.id} already exists."
            ) from exc

    def get(
        self,
        evaluation_id: UUID,
    ) -> WorkflowRunEvaluation | None:
        """Return one run evaluation by evaluation identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM workflow_run_evaluations
                WHERE evaluation_id = ?
                """,
                (str(evaluation_id),),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def evaluations(
        self,
    ) -> tuple[WorkflowRunEvaluation, ...]:
        """Return all run evaluations in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_run_evaluations
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def evaluations_for_run(
        self,
        run_id: UUID,
    ) -> tuple[WorkflowRunEvaluation, ...]:
        """Return evaluations for one workflow run in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_run_evaluations
                WHERE run_id = ?
                ORDER BY sequence
                """,
                (str(run_id),),
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> WorkflowRunEvaluation:
        """Reconstruct one persisted workflow run evaluation."""

        if not isinstance(payload, str):
            raise TypeError("Persisted workflow run evaluation payload was not text.")

        return WorkflowRunEvaluation.model_validate_json(payload)


__all__ = [
    "WORKFLOW_RUN_EVALUATION_TABLES",
    "SqlWorkflowRunEvaluationRepository",
]

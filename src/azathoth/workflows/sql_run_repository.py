"""Durable workflow run evidence, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, IntegrityError, Table
from azathoth.workflows.execution import WorkflowRun

WORKFLOW_RUN_TABLES = (
    Table(
        name="workflow_runs",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_runs (
                sequence {sequence},
                run_id TEXT NOT NULL UNIQUE,
                workflow_id TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_runs_workflow_id_sequence
            ON workflow_runs (
                workflow_id,
                sequence
            )
            """,
        ),
    ),
)
"""The tables workflow runs are kept in."""


class SqlWorkflowRunRepository:
    """Persist immutable workflow run evidence in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(WORKFLOW_RUN_TABLES)

    def save(
        self,
        run: WorkflowRun,
    ) -> None:
        """Persist one workflow run without replacing existing evidence.

        Raises:
            ValueError: A run with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
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
        except IntegrityError as exc:
            raise ValueError(f"Workflow run {run.id} already exists.") from exc

    def get(
        self,
        run_id: UUID,
    ) -> WorkflowRun | None:
        """Return a workflow run by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM workflow_runs
                WHERE run_id = ?
                """,
                (str(run_id),),
            )

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

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_runs
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def runs_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowRun, ...]:
        """Return persisted runs for one workflow in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_runs
                WHERE workflow_id = ?
                ORDER BY sequence
                """,
                (str(workflow_id),),
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> WorkflowRun:
        """Reconstruct one persisted workflow run payload."""

        if not isinstance(payload, str):
            raise TypeError("Persisted workflow run payload was not text.")

        return WorkflowRun.model_validate_json(payload)


__all__ = [
    "WORKFLOW_RUN_TABLES",
    "SqlWorkflowRunRepository",
]

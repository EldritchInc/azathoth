"""Active workflow production state, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, Table, require_text
from azathoth.workflows.production import WorkflowProductionState

WORKFLOW_PRODUCTION_STATE_TABLES = (
    Table(
        name="workflow_production_states",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_production_states (
                sequence {sequence},
                workflow_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            )
            """,
        ),
    ),
)
"""The tables active production states are kept in."""


class SqlWorkflowProductionStateRepository:
    """Persist active workflow production state in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(WORKFLOW_PRODUCTION_STATE_TABLES)

    def set(
        self,
        state: WorkflowProductionState,
    ) -> None:
        """Set the active production state for one workflow.

        A workflow keeps its place in the order it was first promoted.
        """

        workflow_id = state.specification.metadata.id

        with self._database.transaction() as session:
            session.execute(
                """
                INSERT INTO workflow_production_states (
                    workflow_id,
                    payload
                )
                VALUES (?, ?)
                ON CONFLICT (workflow_id)
                DO UPDATE SET
                    payload = excluded.payload
                """,
                (
                    str(workflow_id),
                    state.model_dump_json(),
                ),
            )

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowProductionState | None:
        """Return the active production state for one workflow."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM workflow_production_states
                WHERE workflow_id = ?
                """,
                (str(workflow_id),),
            )

        if row is None:
            return None

        return WorkflowProductionState.model_validate_json(
            require_text(
                row[0],
                f"Persisted workflow production state for {workflow_id} was not text.",
            )
        )

    def states(
        self,
    ) -> tuple[WorkflowProductionState, ...]:
        """Return all active production states in deterministic order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_production_states
                ORDER BY sequence
                """
            )

        return tuple(
            WorkflowProductionState.model_validate_json(
                require_text(row[0], "Persisted workflow production state payload was not text.")
            )
            for row in rows
        )


__all__ = [
    "WORKFLOW_PRODUCTION_STATE_TABLES",
    "SqlWorkflowProductionStateRepository",
]

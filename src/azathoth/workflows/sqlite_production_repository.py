"""SQLite persistence for active workflow production state."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.production import WorkflowProductionState


class SQLiteWorkflowProductionStateRepository:
    """Persist active workflow production state in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)

        self._initialize()

    def set(
        self,
        state: WorkflowProductionState,
    ) -> None:
        """Set the active production state for one workflow."""

        workflow_id = state.specification.metadata.id

        connection = sqlite3.connect(
            self._database,
        )

        try:
            connection.execute(
                """
                INSERT INTO workflow_production_states (
                    workflow_id,
                    payload
                )
                VALUES (?, ?)
                ON CONFLICT(workflow_id)
                DO UPDATE SET
                    payload = excluded.payload
                """,
                (
                    str(workflow_id),
                    state.model_dump_json(),
                ),
            )

            connection.commit()
        finally:
            connection.close()

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowProductionState | None:
        """Return the active production state for one workflow."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_production_states
                WHERE workflow_id = ?
                """,
                (str(workflow_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        payload = row[0]

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError(f"Persisted workflow production state for {workflow_id} was not text.")

        return WorkflowProductionState.model_validate_json(
            payload,
        )

    def states(
        self,
    ) -> tuple[WorkflowProductionState, ...]:
        """Return all active production states in deterministic order."""

        connection = sqlite3.connect(
            self._database,
        )

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_production_states
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        states: list[WorkflowProductionState] = []

        for row in rows:
            payload = row[0]

            if not isinstance(
                payload,
                str,
            ):
                raise TypeError("Persisted workflow production state payload was not text.")

            states.append(
                WorkflowProductionState.model_validate_json(
                    payload,
                )
            )

        return tuple(states)

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
                CREATE TABLE IF NOT EXISTS workflow_production_states (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.commit()
        finally:
            connection.close()

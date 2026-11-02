"""Database persistence for the index of child runs (ADR 0105)."""

from datetime import datetime
from uuid import UUID

from azathoth.persistence import Database, require_integer, require_text
from azathoth.workflows.run_children import RunChild
from azathoth.workflows.run_progress_tables import RUN_CHILD_TABLES


class SqlRunChildRepository:
    """Persist the index of child runs in a database, one row per child."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(RUN_CHILD_TABLES)

    def record(
        self,
        child: RunChild,
    ) -> None:
        """Record one child; a child already recorded is left as it is."""

        with self._database.transaction() as session:
            session.execute(
                """
                INSERT INTO run_children (
                    child_run_id,
                    child_workflow_id,
                    child_invocation_id,
                    parent_run_id,
                    parent_step_id,
                    parent_attempt,
                    root_run_id,
                    depth,
                    recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (child_run_id) DO NOTHING
                """,
                (
                    str(child.child_run_id),
                    str(child.child_workflow_id),
                    None if child.child_invocation_id is None else str(child.child_invocation_id),
                    str(child.parent_run_id),
                    str(child.parent_step_id),
                    child.parent_attempt,
                    str(child.root_run_id),
                    child.depth,
                    child.recorded_at.isoformat(),
                ),
            )

    def children_of(
        self,
        parent_run_id: UUID,
    ) -> tuple[RunChild, ...]:
        """Return a run's children, in the order they started."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT
                    child_run_id,
                    child_workflow_id,
                    child_invocation_id,
                    parent_run_id,
                    parent_step_id,
                    parent_attempt,
                    root_run_id,
                    depth,
                    recorded_at
                FROM run_children
                WHERE parent_run_id = ?
                ORDER BY sequence
                """,
                (str(parent_run_id),),
            )

        return tuple(
            RunChild(
                child_run_id=UUID(require_text(row[0], "Persisted child run ID was not text.")),
                child_workflow_id=UUID(
                    require_text(row[1], "Persisted child workflow ID was not text.")
                ),
                child_invocation_id=(
                    None
                    if row[2] is None
                    else UUID(require_text(row[2], "Persisted child invocation ID was not text."))
                ),
                parent_run_id=UUID(require_text(row[3], "Persisted parent run ID was not text.")),
                parent_step_id=UUID(require_text(row[4], "Persisted parent step ID was not text.")),
                parent_attempt=require_integer(
                    row[5], "Persisted parent attempt was not an integer."
                ),
                root_run_id=UUID(require_text(row[6], "Persisted root run ID was not text.")),
                depth=require_integer(row[7], "Persisted child depth was not an integer."),
                recorded_at=datetime.fromisoformat(
                    require_text(row[8], "Persisted child time was not text.")
                ),
            )
            for row in rows
        )


__all__ = [
    "SqlRunChildRepository",
]

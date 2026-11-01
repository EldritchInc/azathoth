"""Immutable workflow production revisions, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, IntegrityError, Table, require_text
from azathoth.workflows.production import WorkflowProductionRevision

WORKFLOW_PRODUCTION_REVISION_TABLES = (
    Table(
        name="workflow_production_revisions",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_production_revisions (
                sequence {sequence},
                revision_id TEXT NOT NULL UNIQUE,
                workflow_id TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                workflow_production_revisions_workflow_id_sequence
            ON workflow_production_revisions (
                workflow_id,
                sequence
            )
            """,
        ),
    ),
)
"""The tables production revisions are kept in."""


class SqlWorkflowProductionRevisionRepository:
    """Persist immutable workflow production revisions in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(WORKFLOW_PRODUCTION_REVISION_TABLES)

    def save(
        self,
        revision: WorkflowProductionRevision,
    ) -> None:
        """Persist one production revision without replacing history.

        Raises:
            ValueError: A revision with the same identifier already exists.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
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
        except IntegrityError as exc:
            raise ValueError(f"Workflow production revision {revision.id} already exists.") from exc

    def get(
        self,
        revision_id: UUID,
    ) -> WorkflowProductionRevision | None:
        """Return one production revision by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM workflow_production_revisions
                WHERE revision_id = ?
                """,
                (str(revision_id),),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def revisions(
        self,
    ) -> tuple[WorkflowProductionRevision, ...]:
        """Return all production revisions in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_production_revisions
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def revisions_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowProductionRevision, ...]:
        """Return production revisions for one workflow in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_production_revisions
                WHERE workflow_id = ?
                ORDER BY sequence
                """,
                (str(workflow_id),),
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> WorkflowProductionRevision:
        """Reconstruct one persisted workflow production revision."""

        return WorkflowProductionRevision.model_validate_json(
            require_text(payload, "Persisted workflow production revision payload was not text.")
        )


__all__ = [
    "WORKFLOW_PRODUCTION_REVISION_TABLES",
    "SqlWorkflowProductionRevisionRepository",
]

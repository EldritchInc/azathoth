"""SQLite persistence for revisioned workflow specifications."""

from pathlib import Path

from azathoth.persistence import Session, SQLiteDatabase, require_text
from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.revision import WorkflowSpecificationRevision
from azathoth.workflows.sql_repository import (
    SqlWorkflowRepository,
    insert_specification_revision,
)


class SQLiteWorkflowRepository(SqlWorkflowRepository):
    """Persist revisioned workflow specifications in a SQLite database.

    Revisions live in `workflow_specification_revisions`. Databases written
    before revisions existed kept one specification per workflow in
    `workflow_specifications`; opening such a database copies each of those
    specifications in as revision 1, without an import time. The legacy table
    is left in place and never written again.
    """

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        sqlite = SQLiteDatabase(database)

        super().__init__(sqlite)

        with sqlite.transaction() as session:
            _migrate_legacy_specifications(session)


def _migrate_legacy_specifications(
    session: Session,
) -> None:
    """Copy each legacy specification without revisions in as revision 1.

    Legacy rows are copied in their original order, so first-import order is
    preserved. Workflows that already have revisions are left alone, which
    makes the migration safe to run every time a repository opens.
    """

    legacy = session.fetchone(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'workflow_specifications'
        """
    )

    if legacy is None:
        return

    rows = session.fetchall(
        """
        SELECT payload
        FROM workflow_specifications
        WHERE workflow_id NOT IN (
            SELECT workflow_id
            FROM workflow_specification_revisions
        )
        ORDER BY sequence
        """
    )

    for row in rows:
        payload = require_text(row[0], "Persisted workflow specification payload was not text.")

        insert_specification_revision(
            session,
            WorkflowSpecificationRevision.create(
                WorkflowSpecification.model_validate_json(payload),
                number=1,
            ).model_copy(
                update={
                    "imported_at": None,
                },
            ),
        )

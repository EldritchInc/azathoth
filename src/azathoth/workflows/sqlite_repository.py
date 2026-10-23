"""SQLite persistence for revisioned workflow specifications."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.revision import WorkflowSpecificationRevision


class SQLiteWorkflowRepository:
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
        self._database = str(database)
        self._initialize()

    def save(
        self,
        specification: WorkflowSpecification,
    ) -> WorkflowSpecificationRevision:
        """Append one specification as its workflow's next revision.

        The next number is read and written in one immediate transaction, so
        concurrent imports of the same workflow never receive the same number.
        """

        workflow_id = specification.metadata.id

        connection = sqlite3.connect(
            self._database,
            isolation_level=None,
        )

        try:
            connection.execute("BEGIN IMMEDIATE")

            try:
                row = connection.execute(
                    """
                    SELECT COALESCE(MAX(number), 0)
                    FROM workflow_specification_revisions
                    WHERE workflow_id = ?
                    """,
                    (str(workflow_id),),
                ).fetchone()

                revision = WorkflowSpecificationRevision.create(
                    specification,
                    number=int(row[0]) + 1,
                )

                _insert_revision(
                    connection,
                    revision,
                )

                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()

        return revision

    def get(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecification | None:
        """Return a workflow's latest specification."""

        revision = self.latest_revision(workflow_id)

        return revision.specification if revision is not None else None

    def specifications(
        self,
    ) -> tuple[WorkflowSpecification, ...]:
        """Return every workflow's latest specification in first-import order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT latest.payload
                FROM workflow_specification_revisions AS latest
                JOIN (
                    SELECT
                        workflow_id,
                        MIN(sequence) AS first_sequence,
                        MAX(number) AS latest_number
                    FROM workflow_specification_revisions
                    GROUP BY workflow_id
                ) AS lineage
                    ON lineage.workflow_id = latest.workflow_id
                    AND lineage.latest_number = latest.number
                ORDER BY lineage.first_sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(_deserialize_revision(row[0]).specification for row in rows)

    def latest_revision(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecificationRevision | None:
        """Return a workflow's latest revision."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_specification_revisions
                WHERE workflow_id = ?
                ORDER BY number DESC
                LIMIT 1
                """,
                (str(workflow_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return _deserialize_revision(row[0])

    def revision(
        self,
        workflow_id: UUID,
        number: int,
    ) -> WorkflowSpecificationRevision | None:
        """Return one numbered revision of a workflow."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM workflow_specification_revisions
                WHERE workflow_id = ? AND number = ?
                """,
                (
                    str(workflow_id),
                    number,
                ),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return _deserialize_revision(row[0])

    def revisions(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowSpecificationRevision, ...]:
        """Return every revision of a workflow, oldest first."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM workflow_specification_revisions
                WHERE workflow_id = ?
                ORDER BY number
                """,
                (str(workflow_id),),
            ).fetchall()
        finally:
            connection.close()

        return tuple(_deserialize_revision(row[0]) for row in rows)

    def _initialize(self) -> None:
        """Create the revision table and migrate any legacy specifications."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_specification_revisions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    number INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE (
                        workflow_id,
                        number
                    )
                )
                """
            )

            _migrate_legacy_specifications(connection)

            connection.commit()
        finally:
            connection.close()


def _insert_revision(
    connection: sqlite3.Connection,
    revision: WorkflowSpecificationRevision,
) -> None:
    """Insert one revision row."""

    connection.execute(
        """
        INSERT INTO workflow_specification_revisions (
            workflow_id,
            number,
            content_digest,
            payload
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            str(revision.workflow_id),
            revision.number,
            revision.content_digest,
            revision.model_dump_json(),
        ),
    )


def _migrate_legacy_specifications(
    connection: sqlite3.Connection,
) -> None:
    """Copy each legacy specification without revisions in as revision 1.

    Legacy rows are copied in their original order, so first-import order is
    preserved. Workflows that already have revisions are left alone, which
    makes the migration safe to run every time a repository opens.
    """

    legacy = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'workflow_specifications'
        """
    ).fetchone()

    if legacy is None:
        return

    rows = connection.execute(
        """
        SELECT payload
        FROM workflow_specifications
        WHERE workflow_id NOT IN (
            SELECT workflow_id
            FROM workflow_specification_revisions
        )
        ORDER BY sequence
        """
    ).fetchall()

    for row in rows:
        payload = row[0]

        if not isinstance(payload, str):
            raise TypeError("Persisted workflow specification payload was not text.")

        _insert_revision(
            connection,
            WorkflowSpecificationRevision.create(
                WorkflowSpecification.model_validate_json(payload),
                number=1,
            ).model_copy(
                update={
                    "imported_at": None,
                },
            ),
        )


def _deserialize_revision(
    payload: object,
) -> WorkflowSpecificationRevision:
    """Reconstruct one persisted workflow revision.

    Raises:
        TypeError: The persisted payload is not text.
    """

    if not isinstance(payload, str):
        raise TypeError("Persisted workflow revision payload was not text.")

    return WorkflowSpecificationRevision.model_validate_json(payload)

"""Revisioned workflow specifications, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, Session, Table, require_integer, require_text
from azathoth.revisions import (
    PREVIOUS,
    Author,
    Lineage,
    LineageRecord,
    ParentChoice,
    RevisionKind,
    SavedRevision,
    base_record,
    content_digest,
    lineage_records,
    record_lineage,
    tables_with_lineage,
)
from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.revision import WorkflowSpecificationRevision

WORKFLOW_SPECIFICATION_REVISIONS = "workflow_specification_revisions"

WORKFLOW_SPECIFICATION_TABLES = (
    Table(
        name=WORKFLOW_SPECIFICATION_REVISIONS,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS workflow_specification_revisions (
                sequence {sequence},
                workflow_id TEXT NOT NULL,
                number INTEGER NOT NULL,
                content_digest TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (
                    workflow_id,
                    number
                )
            )
            """,
        ),
    ),
)
"""The tables workflow specification revisions are kept in."""


class SqlWorkflowRepository:
    """Persist revisioned workflow specifications in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(tables_with_lineage(WORKFLOW_SPECIFICATION_TABLES))

    def save(
        self,
        specification: WorkflowSpecification,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> WorkflowSpecificationRevision:
        """Append one specification as its workflow's next revision, and return it.

        As `save_revision`, which says when nothing is appended.
        """

        return self.save_revision(
            specification,
            author=author,
            based_on=based_on,
        ).revision

    def save_revision(
        self,
        specification: WorkflowSpecification,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> SavedRevision[WorkflowSpecificationRevision]:
        """Append one specification as its workflow's next revision, built on another.

        It builds on the revision whose revision digest is `based_on`, or on
        the latest without one. A specification identical to the revision
        it builds on appends nothing, and that revision is returned. One
        built on an earlier revision than the latest forks: it is numbered
        after the latest, and its parent is the one it was built on.

        The next number is read and written in one transaction holding the
        revision table's write lock, so concurrent imports of the same
        workflow never receive the same number.

        Raises:
            BaseRevisionError: No revision of the workflow has the digest
                `based_on`.
        """

        workflow_id = specification.metadata.id
        lineage = Lineage(kind=RevisionKind.WORKFLOW, id=workflow_id)

        with self._database.transaction(lock=WORKFLOW_SPECIFICATION_REVISIONS) as session:
            parent = base_record(lineage_records(session, lineage), lineage, based_on)

            if parent is not None:
                built_on = _revision_in(session, workflow_id, parent.number)

                if built_on.content_digest == content_digest(specification):
                    return SavedRevision(revision=built_on, lineage=parent, created=False)

            row = session.fetchone(
                """
                SELECT COALESCE(MAX(number), 0)
                FROM workflow_specification_revisions
                WHERE workflow_id = ?
                """,
                (str(workflow_id),),
            )

            latest = require_integer(
                row[0] if row is not None else None,
                "The latest workflow revision number was not an integer.",
            )

            revision = WorkflowSpecificationRevision.create(
                specification,
                number=latest + 1,
            )

            record = insert_specification_revision(
                session,
                revision,
                author=author,
                parent=parent,
            )

        return SavedRevision(revision=revision, lineage=record, created=True)

    def lineage(
        self,
        workflow_id: UUID,
    ) -> tuple[LineageRecord, ...]:
        """Return the lineage record of every revision of a workflow, oldest first."""

        with self._database.transaction() as session:
            return lineage_records(
                session,
                Lineage(kind=RevisionKind.WORKFLOW, id=workflow_id),
            )

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

        with self._database.transaction() as session:
            rows = session.fetchall(
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
            )

        return tuple(_deserialize_revision(row[0]).specification for row in rows)

    def latest_revision(
        self,
        workflow_id: UUID,
    ) -> WorkflowSpecificationRevision | None:
        """Return a workflow's latest revision."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM workflow_specification_revisions
                WHERE workflow_id = ?
                ORDER BY number DESC
                LIMIT 1
                """,
                (str(workflow_id),),
            )

        if row is None:
            return None

        return _deserialize_revision(row[0])

    def revision(
        self,
        workflow_id: UUID,
        number: int,
    ) -> WorkflowSpecificationRevision | None:
        """Return one numbered revision of a workflow."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM workflow_specification_revisions
                WHERE workflow_id = ? AND number = ?
                """,
                (
                    str(workflow_id),
                    number,
                ),
            )

        if row is None:
            return None

        return _deserialize_revision(row[0])

    def revisions(
        self,
        workflow_id: UUID,
    ) -> tuple[WorkflowSpecificationRevision, ...]:
        """Return every revision of a workflow, oldest first."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM workflow_specification_revisions
                WHERE workflow_id = ?
                ORDER BY number
                """,
                (str(workflow_id),),
            )

        return tuple(_deserialize_revision(row[0]) for row in rows)


def insert_specification_revision(
    session: Session,
    revision: WorkflowSpecificationRevision,
    *,
    author: Author | None = None,
    parent: ParentChoice = PREVIOUS,
) -> LineageRecord:
    """Insert one revision row, record its lineage (ADR 0122), and return that record.

    By default its parent is the revision numbered before it.
    """

    session.execute(
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

    return record_lineage(
        session,
        Lineage(
            kind=RevisionKind.WORKFLOW,
            id=revision.workflow_id,
        ),
        number=revision.number,
        content_digest=revision.content_digest,
        author=author,
        parent=parent,
    )


def _revision_in(
    session: Session,
    workflow_id: UUID,
    number: int,
) -> WorkflowSpecificationRevision:
    """Return one numbered revision of a workflow, read in an open transaction.

    Raises:
        LookupError: The workflow has no revision with that number.
    """

    row = session.fetchone(
        """
        SELECT payload
        FROM workflow_specification_revisions
        WHERE workflow_id = ? AND number = ?
        """,
        (str(workflow_id), number),
    )

    if row is None:
        raise LookupError(f"Workflow {workflow_id} has no revision {number}.")

    return _deserialize_revision(row[0])


def _deserialize_revision(
    payload: object,
) -> WorkflowSpecificationRevision:
    """Reconstruct one persisted workflow revision.

    Raises:
        TypeError: The persisted payload is not text.
    """

    return WorkflowSpecificationRevision.model_validate_json(
        require_text(payload, "Persisted workflow revision payload was not text.")
    )


__all__ = [
    "WORKFLOW_SPECIFICATION_REVISIONS",
    "WORKFLOW_SPECIFICATION_TABLES",
    "SqlWorkflowRepository",
    "insert_specification_revision",
]

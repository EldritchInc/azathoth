"""Revisioned benchmark datasets, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.evaluation.benchmark_revision import BenchmarkDatasetRevision
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

BENCHMARK_DATASET_REVISIONS = "benchmark_dataset_revisions"

BENCHMARK_TABLES = (
    Table(
        name=BENCHMARK_DATASET_REVISIONS,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS benchmark_dataset_revisions (
                sequence {sequence},
                dataset_id TEXT NOT NULL,
                number INTEGER NOT NULL,
                content_digest TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (
                    dataset_id,
                    number
                )
            )
            """,
        ),
    ),
)
"""The tables benchmark dataset revisions are kept in."""


class SqlBenchmarkRepository:
    """Persist revisioned benchmark datasets in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(tables_with_lineage(BENCHMARK_TABLES))

    def save(
        self,
        dataset: BenchmarkDataset,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> BenchmarkDatasetRevision:
        """Append one dataset as its benchmark's next revision, and return it.

        As `save_revision`, which says when nothing is appended.
        """

        return self.save_revision(
            dataset,
            author=author,
            based_on=based_on,
        ).revision

    def save_revision(
        self,
        dataset: BenchmarkDataset,
        *,
        author: Author | None = None,
        based_on: str | None = None,
    ) -> SavedRevision[BenchmarkDatasetRevision]:
        """Append one dataset as its benchmark's next revision, built on another.

        It builds on the revision whose revision digest is `based_on`, or on
        the latest without one. A dataset identical to the revision it
        builds on appends nothing, and that revision is returned. One built
        on an earlier revision than the latest forks: it is numbered after
        the latest, and its parent is the one it was built on.

        The next number is read and written in one transaction holding the
        revision table's write lock, so concurrent imports of the same
        benchmark never receive the same number.

        Raises:
            BaseRevisionError: No revision of the benchmark has the digest
                `based_on`.
        """

        lineage = Lineage(kind=RevisionKind.BENCHMARK, id=dataset.id)

        with self._database.transaction(lock=BENCHMARK_DATASET_REVISIONS) as session:
            parent = base_record(lineage_records(session, lineage), lineage, based_on)

            if parent is not None:
                built_on = _revision_in(session, dataset.id, parent.number)

                if built_on.content_digest == content_digest(dataset):
                    return SavedRevision(revision=built_on, lineage=parent, created=False)

            row = session.fetchone(
                """
                SELECT COALESCE(MAX(number), 0)
                FROM benchmark_dataset_revisions
                WHERE dataset_id = ?
                """,
                (str(dataset.id),),
            )

            latest = require_integer(
                row[0] if row is not None else None,
                "The latest benchmark revision number was not an integer.",
            )

            revision = BenchmarkDatasetRevision.create(
                dataset,
                number=latest + 1,
            )

            record = insert_benchmark_revision(
                session,
                revision,
                author=author,
                parent=parent,
            )

        return SavedRevision(revision=revision, lineage=record, created=True)

    def lineage(
        self,
        dataset_id: UUID,
    ) -> tuple[LineageRecord, ...]:
        """Return the lineage record of every revision of a benchmark, oldest first."""

        with self._database.transaction() as session:
            return lineage_records(
                session,
                Lineage(kind=RevisionKind.BENCHMARK, id=dataset_id),
            )

    def get(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDataset | None:
        """Return a benchmark's latest dataset."""

        revision = self.latest_revision(dataset_id)

        return revision.dataset if revision is not None else None

    def datasets(
        self,
    ) -> tuple[BenchmarkDataset, ...]:
        """Return every benchmark's latest dataset in first-import order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT latest.payload
                FROM benchmark_dataset_revisions AS latest
                JOIN (
                    SELECT
                        dataset_id,
                        MIN(sequence) AS first_sequence,
                        MAX(number) AS latest_number
                    FROM benchmark_dataset_revisions
                    GROUP BY dataset_id
                ) AS lineage
                    ON lineage.dataset_id = latest.dataset_id
                    AND lineage.latest_number = latest.number
                ORDER BY lineage.first_sequence
                """
            )

        return tuple(_deserialize_revision(row[0]).dataset for row in rows)

    def latest_revision(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDatasetRevision | None:
        """Return a benchmark's latest revision."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM benchmark_dataset_revisions
                WHERE dataset_id = ?
                ORDER BY number DESC
                LIMIT 1
                """,
                (str(dataset_id),),
            )

        if row is None:
            return None

        return _deserialize_revision(row[0])

    def revision(
        self,
        dataset_id: UUID,
        number: int,
    ) -> BenchmarkDatasetRevision | None:
        """Return one numbered revision of a benchmark."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM benchmark_dataset_revisions
                WHERE dataset_id = ? AND number = ?
                """,
                (
                    str(dataset_id),
                    number,
                ),
            )

        if row is None:
            return None

        return _deserialize_revision(row[0])

    def revisions(
        self,
        dataset_id: UUID,
    ) -> tuple[BenchmarkDatasetRevision, ...]:
        """Return every revision of a benchmark, oldest first."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM benchmark_dataset_revisions
                WHERE dataset_id = ?
                ORDER BY number
                """,
                (str(dataset_id),),
            )

        return tuple(_deserialize_revision(row[0]) for row in rows)


def insert_benchmark_revision(
    session: Session,
    revision: BenchmarkDatasetRevision,
    *,
    author: Author | None = None,
    parent: ParentChoice = PREVIOUS,
) -> LineageRecord:
    """Insert one revision row, record its lineage (ADR 0122), and return that record.

    By default its parent is the revision numbered before it.
    """

    session.execute(
        """
        INSERT INTO benchmark_dataset_revisions (
            dataset_id,
            number,
            content_digest,
            payload
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            str(revision.dataset_id),
            revision.number,
            revision.content_digest,
            revision.model_dump_json(),
        ),
    )

    return record_lineage(
        session,
        Lineage(
            kind=RevisionKind.BENCHMARK,
            id=revision.dataset_id,
        ),
        number=revision.number,
        content_digest=revision.content_digest,
        author=author,
        parent=parent,
    )


def _revision_in(
    session: Session,
    dataset_id: UUID,
    number: int,
) -> BenchmarkDatasetRevision:
    """Return one numbered revision of a benchmark, read in an open transaction.

    Raises:
        LookupError: The benchmark has no revision with that number.
    """

    row = session.fetchone(
        """
        SELECT payload
        FROM benchmark_dataset_revisions
        WHERE dataset_id = ? AND number = ?
        """,
        (str(dataset_id), number),
    )

    if row is None:
        raise LookupError(f"Benchmark {dataset_id} has no revision {number}.")

    return _deserialize_revision(row[0])


def _deserialize_revision(
    payload: object,
) -> BenchmarkDatasetRevision:
    """Reconstruct one persisted benchmark revision.

    Raises:
        TypeError: The persisted payload is not text.
    """

    return BenchmarkDatasetRevision.model_validate_json(
        require_text(payload, "Persisted benchmark revision payload was not text.")
    )


__all__ = [
    "BENCHMARK_DATASET_REVISIONS",
    "BENCHMARK_TABLES",
    "SqlBenchmarkRepository",
    "insert_benchmark_revision",
]

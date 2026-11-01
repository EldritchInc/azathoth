"""Revisioned benchmark datasets, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.evaluation.benchmark_revision import BenchmarkDatasetRevision
from azathoth.persistence import Database, Session, Table, require_integer, require_text

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
        database.prepare(BENCHMARK_TABLES)

    def save(
        self,
        dataset: BenchmarkDataset,
    ) -> BenchmarkDatasetRevision:
        """Append one dataset as its benchmark's next revision.

        The next number is read and written in one transaction holding the
        revision table's write lock, so concurrent imports of the same
        benchmark never receive the same number.
        """

        with self._database.transaction(lock=BENCHMARK_DATASET_REVISIONS) as session:
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

            insert_benchmark_revision(session, revision)

        return revision

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
) -> None:
    """Insert one revision row."""

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

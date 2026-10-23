"""SQLite persistence for revisioned benchmark datasets."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.evaluation.benchmark_revision import BenchmarkDatasetRevision


class SQLiteBenchmarkRepository:
    """Persist revisioned benchmark datasets in a SQLite database.

    Revisions live in `benchmark_dataset_revisions`. Databases written before
    revisions existed kept one dataset per benchmark in `benchmark_datasets`;
    opening such a database copies each of those datasets in as revision 1,
    without an import time. The legacy table is left in place and never
    written again.
    """

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        dataset: BenchmarkDataset,
    ) -> BenchmarkDatasetRevision:
        """Append one dataset as its benchmark's next revision.

        The next number is read and written in one immediate transaction, so
        concurrent imports of the same benchmark never receive the same number.
        """

        dataset_id = dataset.id

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
                    FROM benchmark_dataset_revisions
                    WHERE dataset_id = ?
                    """,
                    (str(dataset_id),),
                ).fetchone()

                revision = BenchmarkDatasetRevision.create(
                    dataset,
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
        dataset_id: UUID,
    ) -> BenchmarkDataset | None:
        """Return a benchmark's latest dataset."""

        revision = self.latest_revision(dataset_id)

        return revision.dataset if revision is not None else None

    def datasets(
        self,
    ) -> tuple[BenchmarkDataset, ...]:
        """Return every benchmark's latest dataset in first-import order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
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
            ).fetchall()
        finally:
            connection.close()

        return tuple(_deserialize_revision(row[0]).dataset for row in rows)

    def latest_revision(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDatasetRevision | None:
        """Return a benchmark's latest revision."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM benchmark_dataset_revisions
                WHERE dataset_id = ?
                ORDER BY number DESC
                LIMIT 1
                """,
                (str(dataset_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return _deserialize_revision(row[0])

    def revision(
        self,
        dataset_id: UUID,
        number: int,
    ) -> BenchmarkDatasetRevision | None:
        """Return one numbered revision of a benchmark."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM benchmark_dataset_revisions
                WHERE dataset_id = ? AND number = ?
                """,
                (
                    str(dataset_id),
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
        dataset_id: UUID,
    ) -> tuple[BenchmarkDatasetRevision, ...]:
        """Return every revision of a benchmark, oldest first."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM benchmark_dataset_revisions
                WHERE dataset_id = ?
                ORDER BY number
                """,
                (str(dataset_id),),
            ).fetchall()
        finally:
            connection.close()

        return tuple(_deserialize_revision(row[0]) for row in rows)

    def _initialize(self) -> None:
        """Create the revision table and migrate any legacy datasets."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_dataset_revisions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    number INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE (
                        dataset_id,
                        number
                    )
                )
                """
            )

            _migrate_legacy_datasets(connection)

            connection.commit()
        finally:
            connection.close()


def _insert_revision(
    connection: sqlite3.Connection,
    revision: BenchmarkDatasetRevision,
) -> None:
    """Insert one revision row."""

    connection.execute(
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


def _migrate_legacy_datasets(
    connection: sqlite3.Connection,
) -> None:
    """Copy each legacy dataset without revisions in as revision 1.

    Legacy rows are copied in their original order, so first-import order is
    preserved. Benchmarks that already have revisions are left alone, which
    makes the migration safe to run every time a repository opens.
    """

    legacy = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'benchmark_datasets'
        """
    ).fetchone()

    if legacy is None:
        return

    rows = connection.execute(
        """
        SELECT payload
        FROM benchmark_datasets
        WHERE dataset_id NOT IN (
            SELECT dataset_id
            FROM benchmark_dataset_revisions
        )
        ORDER BY sequence
        """
    ).fetchall()

    for row in rows:
        payload = row[0]

        if not isinstance(payload, str):
            raise TypeError("Persisted benchmark dataset payload was not text.")

        _insert_revision(
            connection,
            BenchmarkDatasetRevision.create(
                BenchmarkDataset.model_validate_json(payload),
                number=1,
            ).model_copy(
                update={
                    "imported_at": None,
                },
            ),
        )


def _deserialize_revision(
    payload: object,
) -> BenchmarkDatasetRevision:
    """Reconstruct one persisted benchmark revision.

    Raises:
        TypeError: The persisted payload is not text.
    """

    if not isinstance(payload, str):
        raise TypeError("Persisted benchmark revision payload was not text.")

    return BenchmarkDatasetRevision.model_validate_json(payload)

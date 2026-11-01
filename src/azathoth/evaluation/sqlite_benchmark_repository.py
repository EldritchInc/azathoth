"""SQLite persistence for revisioned benchmark datasets."""

from pathlib import Path

from azathoth.evaluation.benchmark import BenchmarkDataset
from azathoth.evaluation.benchmark_revision import BenchmarkDatasetRevision
from azathoth.evaluation.sql_benchmark_repository import (
    SqlBenchmarkRepository,
    insert_benchmark_revision,
)
from azathoth.persistence import Session, SQLiteDatabase, require_text


class SQLiteBenchmarkRepository(SqlBenchmarkRepository):
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
        sqlite = SQLiteDatabase(database)

        super().__init__(sqlite)

        with sqlite.transaction() as session:
            _migrate_legacy_datasets(session)


def _migrate_legacy_datasets(
    session: Session,
) -> None:
    """Copy each legacy dataset without revisions in as revision 1.

    Legacy rows are copied in their original order, so first-import order is
    preserved. Benchmarks that already have revisions are left alone, which
    makes the migration safe to run every time a repository opens.
    """

    legacy = session.fetchone(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'benchmark_datasets'
        """
    )

    if legacy is None:
        return

    rows = session.fetchall(
        """
        SELECT payload
        FROM benchmark_datasets
        WHERE dataset_id NOT IN (
            SELECT dataset_id
            FROM benchmark_dataset_revisions
        )
        ORDER BY sequence
        """
    )

    for row in rows:
        payload = require_text(row[0], "Persisted benchmark dataset payload was not text.")

        insert_benchmark_revision(
            session,
            BenchmarkDatasetRevision.create(
                BenchmarkDataset.model_validate_json(payload),
                number=1,
            ).model_copy(
                update={
                    "imported_at": None,
                },
            ),
        )

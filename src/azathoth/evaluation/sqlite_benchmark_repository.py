"""SQLite persistence for reusable benchmark datasets."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.evaluation.benchmark import BenchmarkDataset


class SQLiteBenchmarkRepository:
    """Persist immutable benchmark datasets in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        self._database = str(database)
        self._initialize()

    def save(
        self,
        dataset: BenchmarkDataset,
    ) -> None:
        """Persist one dataset without replacing existing configuration."""

        connection = sqlite3.connect(self._database)

        try:
            try:
                connection.execute(
                    """
                    INSERT INTO benchmark_datasets (
                        dataset_id,
                        name,
                        version,
                        payload
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(dataset.id),
                        dataset.name,
                        dataset.version,
                        dataset.model_dump_json(),
                    ),
                )

                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Benchmark dataset {dataset.id} already exists.") from exc
        finally:
            connection.close()

    def get(
        self,
        dataset_id: UUID,
    ) -> BenchmarkDataset | None:
        """Return one benchmark dataset by identifier."""

        connection = sqlite3.connect(self._database)

        try:
            row = connection.execute(
                """
                SELECT payload
                FROM benchmark_datasets
                WHERE dataset_id = ?
                """,
                (str(dataset_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def datasets(
        self,
    ) -> tuple[BenchmarkDataset, ...]:
        """Return all benchmark datasets in insertion order."""

        connection = sqlite3.connect(self._database)

        try:
            rows = connection.execute(
                """
                SELECT payload
                FROM benchmark_datasets
                ORDER BY sequence
                """
            ).fetchall()
        finally:
            connection.close()

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> BenchmarkDataset:
        """Reconstruct one persisted benchmark dataset."""

        if not isinstance(
            payload,
            str,
        ):
            raise TypeError("Persisted benchmark dataset payload was not text.")

        return BenchmarkDataset.model_validate_json(payload)

    def _initialize(
        self,
    ) -> None:
        """Create repository tables when they do not already exist."""

        connection = sqlite3.connect(self._database)

        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_datasets (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    benchmark_datasets_name_version
                ON benchmark_datasets (
                    name,
                    version,
                    sequence
                )
                """
            )

            connection.commit()
        finally:
            connection.close()

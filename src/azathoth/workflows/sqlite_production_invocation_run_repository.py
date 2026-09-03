"""SQLite persistence for production invocation run associations."""

import sqlite3
from pathlib import Path
from uuid import UUID

from azathoth.workflows.production_invocation_run import (
    ProductionInvocationRun,
)


class SQLiteProductionInvocationRunRepository:
    """Persist production invocation run associations in SQLite."""

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        """Initialize SQLite invocation run persistence."""

        self._path = str(path)
        self._initialize()

    def _connect(
        self,
    ) -> sqlite3.Connection:
        """Open a SQLite connection."""

        return sqlite3.connect(
            self._path,
        )

    def _initialize(
        self,
    ) -> None:
        """Create invocation run persistence when absent."""

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS production_invocation_runs (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    invocation_id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def save(
        self,
        association: ProductionInvocationRun,
    ) -> None:
        """Persist one immutable invocation run association."""

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO production_invocation_runs (
                        invocation_id,
                        run_id,
                        payload
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        str(association.invocation_id),
                        str(association.run_id),
                        association.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("Production invocation already has a workflow run.") from error

    def get(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocationRun | None:
        """Return the run association for one production invocation."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload
                FROM production_invocation_runs
                WHERE invocation_id = ?
                """,
                (str(invocation_id),),
            ).fetchone()

        if row is None:
            return None

        return ProductionInvocationRun.model_validate_json(row[0])

    def associations(
        self,
    ) -> tuple[ProductionInvocationRun, ...]:
        """Return invocation run associations in insertion order."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM production_invocation_runs
                ORDER BY sequence
                """
            ).fetchall()

        return tuple(ProductionInvocationRun.model_validate_json(row[0]) for row in rows)

"""Production invocation run associations, in either database (ADR 0102)."""

from uuid import UUID

from azathoth.persistence import Database, IntegrityError, Table, require_text
from azathoth.workflows.production_invocation_run import (
    ProductionInvocationRun,
)

PRODUCTION_INVOCATION_RUN_TABLES = (
    Table(
        name="production_invocation_runs",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS production_invocation_runs (
                sequence {sequence},
                invocation_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """,
        ),
    ),
)
"""The tables production invocation run associations are kept in."""


class SqlProductionInvocationRunRepository:
    """Persist production invocation run associations in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(PRODUCTION_INVOCATION_RUN_TABLES)

    def save(
        self,
        association: ProductionInvocationRun,
    ) -> None:
        """Persist one immutable invocation run association.

        Raises:
            ValueError: The invocation already has a workflow run.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
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
        except IntegrityError as error:
            raise ValueError("Production invocation already has a workflow run.") from error

    def get(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocationRun | None:
        """Return the run association for one production invocation."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM production_invocation_runs
                WHERE invocation_id = ?
                """,
                (str(invocation_id),),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def associations(
        self,
    ) -> tuple[ProductionInvocationRun, ...]:
        """Return invocation run associations in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM production_invocation_runs
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> ProductionInvocationRun:
        """Reconstruct one persisted invocation run association."""

        return ProductionInvocationRun.model_validate_json(
            require_text(payload, "Persisted production invocation run payload was not text.")
        )


__all__ = [
    "PRODUCTION_INVOCATION_RUN_TABLES",
    "SqlProductionInvocationRunRepository",
]

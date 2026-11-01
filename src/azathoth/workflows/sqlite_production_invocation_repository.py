"""SQLite persistence for production workflow invocations."""

from pathlib import Path

from azathoth.persistence import Session, SQLiteDatabase
from azathoth.workflows.sql_production_invocation_repository import (
    SqlProductionInvocationRepository,
)

_IDEMPOTENCY_COLUMNS = (
    "idempotency_key",
    "request_digest",
)


class SQLiteProductionInvocationRepository(SqlProductionInvocationRepository):
    """Persist production invocations and terminal results in SQLite.

    Opening a database migrates earlier invocation schemas first: a table
    that kept obsolete revision identity loses it, and a table from before
    ADR 0097 gains the idempotency columns in place, keeping every invocation
    and its sequence.
    """

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        sqlite = SQLiteDatabase(database)

        with sqlite.transaction() as session:
            if _requires_revision_column_migration(session):
                _migrate_revision_column(session)

            _add_missing_idempotency_columns(session)

        super().__init__(sqlite)


def _columns(
    session: Session,
) -> set[object]:
    """Return the columns of the invocation table, or none when it does not exist."""

    return {row[1] for row in session.fetchall("PRAGMA table_info(production_invocations)")}


def _add_missing_idempotency_columns(
    session: Session,
) -> None:
    """Add the idempotency columns an earlier invocation table lacks."""

    columns = _columns(session)

    if not columns:
        return

    for column in _IDEMPOTENCY_COLUMNS:
        if column not in columns:
            session.execute(f"ALTER TABLE production_invocations ADD COLUMN {column} TEXT")


def _requires_revision_column_migration(
    session: Session,
) -> bool:
    """Return whether the invocation table retains obsolete revision identity."""

    return "production_revision_id" in _columns(session)


def _migrate_revision_column(
    session: Session,
) -> None:
    """Remove obsolete revision identity while preserving invocation history."""

    session.execute(
        """
        ALTER TABLE production_invocations
        RENAME TO production_invocations_with_revision
        """
    )

    session.execute(
        """
        CREATE TABLE production_invocations (
            sequence {sequence},
            invocation_id TEXT NOT NULL UNIQUE,
            workflow_id TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )

    session.execute(
        """
        INSERT INTO production_invocations (
            sequence,
            invocation_id,
            workflow_id,
            payload
        )
        SELECT
            sequence,
            invocation_id,
            workflow_id,
            payload
        FROM production_invocations_with_revision
        ORDER BY sequence
        """
    )

    session.execute(
        """
        DROP TABLE production_invocations_with_revision
        """
    )

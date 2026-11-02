"""Database persistence for run journals (ADR 0105)."""

from uuid import UUID

from azathoth.persistence import Database, IntegrityError, require_text
from azathoth.workflows.run_journal import (
    RunJournalEntry,
    RunJournalPositionTakenError,
)
from azathoth.workflows.run_progress_tables import RUN_JOURNAL_TABLES


class SqlRunJournalRepository:
    """Persist run journals in a database, one row per entry."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(RUN_JOURNAL_TABLES)

    def append(
        self,
        entry: RunJournalEntry,
    ) -> None:
        """Record one entry.

        Raises:
            RunJournalPositionTakenError: The run already records an entry
                at this position. Nothing is recorded.
        """

        try:
            with self._database.transaction() as session:
                session.execute(
                    """
                    INSERT INTO run_journal (
                        run_id,
                        position,
                        workflow_id,
                        invocation_id,
                        event_type,
                        recorded_at,
                        payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(entry.run_id),
                        entry.position,
                        str(entry.workflow_id),
                        None if entry.invocation_id is None else str(entry.invocation_id),
                        entry.event.type,
                        entry.recorded_at.isoformat(),
                        entry.model_dump_json(),
                    ),
                )
        except IntegrityError as error:
            raise RunJournalPositionTakenError(entry.run_id, entry.position) from error

    def entries(
        self,
        run_id: UUID,
    ) -> tuple[RunJournalEntry, ...]:
        """Return every entry of one run's journal, in position order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM run_journal
                WHERE run_id = ?
                ORDER BY position
                """,
                (str(run_id),),
            )

        return tuple(
            RunJournalEntry.model_validate_json(
                require_text(row[0], "Persisted run journal payload was not text.")
            )
            for row in rows
        )

    def invocation_run_id(
        self,
        invocation_id: UUID,
    ) -> UUID | None:
        """Return the run whose journal records this invocation, if one does."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT run_id
                FROM run_journal
                WHERE invocation_id = ? AND position = 1
                ORDER BY sequence
                """,
                (str(invocation_id),),
            )

        if row is None:
            return None

        return UUID(require_text(row[0], "Persisted run journal run ID was not text."))


__all__ = [
    "SqlRunJournalRepository",
]

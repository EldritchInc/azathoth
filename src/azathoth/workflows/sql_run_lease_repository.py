"""Database persistence for run leases (ADR 0105)."""

from datetime import datetime, timedelta
from uuid import UUID

from azathoth.persistence import Database, Row, Session, require_text
from azathoth.workflows.run_lease import (
    RunLease,
    RunLeaseHeldError,
    RunLeaseLostError,
)
from azathoth.workflows.run_progress_tables import RUN_LEASE_TABLES


class SqlRunLeaseRepository:
    """Persist run leases in a database, one row per run.

    Acquiring and renewing lock the table, so two processes racing for one
    run's lease are serialized, and exactly one of them holds it.
    """

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(RUN_LEASE_TABLES)

    def acquire(
        self,
        run_id: UUID,
        *,
        holder: str,
        now: datetime,
        duration: timedelta,
    ) -> RunLease:
        """Acquire the run's lease, taking over one that has lapsed.

        Raises:
            RunLeaseHeldError: Another holder's lease is live. Nothing changes.
        """

        lease = RunLease(
            run_id=run_id,
            holder=holder,
            acquired_at=now,
            expires_at=now + duration,
        )

        with self._database.transaction(lock="run_leases") as session:
            existing = _lease(session, run_id)

            if existing is not None and existing.holder != holder and not existing.expired(now):
                raise RunLeaseHeldError(existing)

            session.execute("DELETE FROM run_leases WHERE run_id = ?", (str(run_id),))
            session.execute(
                """
                INSERT INTO run_leases (run_id, holder, acquired_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(run_id),
                    holder,
                    lease.acquired_at.isoformat(),
                    lease.expires_at.isoformat(),
                ),
            )

        return lease

    def renew(
        self,
        run_id: UUID,
        *,
        holder: str,
        now: datetime,
        duration: timedelta,
    ) -> RunLease:
        """Move the holder's lease forward to expire `duration` after now.

        Raises:
            RunLeaseLostError: The holder no longer holds the run's lease.
        """

        with self._database.transaction(lock="run_leases") as session:
            existing = _lease(session, run_id)

            if existing is None or existing.holder != holder:
                raise RunLeaseLostError.taken_over(run_id)

            lease = existing.model_copy(update={"expires_at": now + duration})

            session.execute(
                "UPDATE run_leases SET expires_at = ? WHERE run_id = ? AND holder = ?",
                (lease.expires_at.isoformat(), str(run_id), holder),
            )

        return lease

    def release(
        self,
        run_id: UUID,
        *,
        holder: str,
    ) -> None:
        """Release the holder's lease, if it still holds it."""

        with self._database.transaction() as session:
            session.execute(
                "DELETE FROM run_leases WHERE run_id = ? AND holder = ?",
                (str(run_id), holder),
            )

    def get(
        self,
        run_id: UUID,
    ) -> RunLease | None:
        """Return the run's lease, live or lapsed, if one is recorded."""

        with self._database.transaction() as session:
            return _lease(session, run_id)


def _lease(
    session: Session,
    run_id: UUID,
) -> RunLease | None:
    """Return the run's recorded lease in this transaction, if there is one."""

    row: Row | None = session.fetchone(
        """
        SELECT run_id, holder, acquired_at, expires_at
        FROM run_leases
        WHERE run_id = ?
        """,
        (str(run_id),),
    )

    if row is None:
        return None

    return RunLease(
        run_id=UUID(require_text(row[0], "Persisted lease run ID was not text.")),
        holder=require_text(row[1], "Persisted lease holder was not text."),
        acquired_at=datetime.fromisoformat(
            require_text(row[2], "Persisted lease acquisition time was not text.")
        ),
        expires_at=datetime.fromisoformat(
            require_text(row[3], "Persisted lease expiry was not text.")
        ),
    )


__all__ = [
    "SqlRunLeaseRepository",
]

"""The last portfolio read from each remote, and when, so status can be told offline (ADR 0125).

Status reads a remote's portfolio whenever it reaches the remote, and keeps
what it read here, one snapshot per remote URL, each read replacing the
last. When the remote cannot be reached, status says which models it had
authorized as of the snapshot's time.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict

from azathoth.persistence import Database, SQLiteDatabase, Table, require_text
from azathoth.remote.client import require_remote_url
from azathoth.remote.records import PortfolioResponse

REMOTE_PORTFOLIO_SNAPSHOT_TABLES: Final = (
    Table(
        name="remote_portfolio_snapshots",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                remote_portfolio_snapshots (
                    remote TEXT NOT NULL PRIMARY KEY,
                    synced_at TEXT NOT NULL,
                    portfolio TEXT NOT NULL
                )
            """,
        ),
    ),
)
"""The table the last portfolio read from each remote is kept in (ADR 0125).

Snapshots were first taken in this version, so there is nothing to
backfill.
"""


class PortfolioSnapshot(BaseModel):
    """One remote's portfolio, as it was when last read, and when that was."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    remote: str

    synced_at: AwareDatetime

    portfolio: PortfolioResponse


class RemotePortfolioSnapshotRepository(Protocol):
    """The last portfolio read from each remote."""

    def save(
        self,
        remote: str,
        portfolio: PortfolioResponse,
    ) -> PortfolioSnapshot:
        """Keep a remote's portfolio as read now, replacing its last snapshot."""

        ...

    def get(
        self,
        remote: str,
    ) -> PortfolioSnapshot | None:
        """Return a remote's last snapshot, or None when its portfolio was never read."""

        ...

    def delete(
        self,
        remote: str,
    ) -> None:
        """Forget a remote's snapshot, if there is one."""

        ...


class SqlRemotePortfolioSnapshotRepository:
    """The last portfolio read from each remote, kept in a database."""

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._database = database
        self._clock = clock
        database.prepare(REMOTE_PORTFOLIO_SNAPSHOT_TABLES)

    def save(
        self,
        remote: str,
        portfolio: PortfolioResponse,
    ) -> PortfolioSnapshot:
        """Keep a remote's portfolio as read now, replacing its last snapshot.

        Raises:
            ValueError: The remote's URL is not an http or https URL.
        """

        snapshot = PortfolioSnapshot(
            remote=require_remote_url(remote),
            synced_at=self._clock(),
            portfolio=portfolio,
        )

        with self._database.transaction() as session:
            session.execute(
                """
                DELETE FROM remote_portfolio_snapshots
                WHERE remote = ?
                """,
                (snapshot.remote,),
            )
            session.execute(
                """
                INSERT INTO remote_portfolio_snapshots (
                    remote,
                    synced_at,
                    portfolio
                )
                VALUES (?, ?, ?)
                """,
                (
                    snapshot.remote,
                    snapshot.synced_at.isoformat(),
                    portfolio.model_dump_json(),
                ),
            )

        return snapshot

    def get(
        self,
        remote: str,
    ) -> PortfolioSnapshot | None:
        """Return a remote's last snapshot, or None when its portfolio was never read.

        Raises:
            ValueError: The remote's URL is not an http or https URL.
        """

        url = require_remote_url(remote)

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT synced_at, portfolio
                FROM remote_portfolio_snapshots
                WHERE remote = ?
                """,
                (url,),
            )

        if row is None:
            return None

        return PortfolioSnapshot(
            remote=url,
            synced_at=datetime.fromisoformat(
                require_text(row[0], "A remote portfolio snapshot's time was not text.")
            ),
            portfolio=PortfolioResponse.model_validate_json(
                require_text(row[1], "A remote portfolio snapshot was not text.")
            ),
        )

    def delete(
        self,
        remote: str,
    ) -> None:
        """Forget a remote's snapshot, if there is one.

        Raises:
            ValueError: The remote's URL is not an http or https URL.
        """

        with self._database.transaction() as session:
            session.execute(
                """
                DELETE FROM remote_portfolio_snapshots
                WHERE remote = ?
                """,
                (require_remote_url(remote),),
            )


class SQLiteRemotePortfolioSnapshotRepository(SqlRemotePortfolioSnapshotRepository):
    """The last portfolio read from each remote, kept in SQLite."""

    def __init__(
        self,
        database: str | Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__(SQLiteDatabase(database), clock=clock)


class InMemoryRemotePortfolioSnapshotRepository:
    """The last portfolio read from each remote, kept in memory, as tests keep it."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._clock = clock
        self._snapshots: dict[str, PortfolioSnapshot] = {}

    def save(
        self,
        remote: str,
        portfolio: PortfolioResponse,
    ) -> PortfolioSnapshot:
        """Keep a remote's portfolio as read now, replacing its last snapshot."""

        snapshot = PortfolioSnapshot(
            remote=require_remote_url(remote),
            synced_at=self._clock(),
            portfolio=portfolio,
        )
        self._snapshots[snapshot.remote] = snapshot

        return snapshot

    def get(
        self,
        remote: str,
    ) -> PortfolioSnapshot | None:
        """Return a remote's last snapshot, or None when its portfolio was never read."""

        return self._snapshots.get(require_remote_url(remote))

    def delete(
        self,
        remote: str,
    ) -> None:
        """Forget a remote's snapshot, if there is one."""

        self._snapshots.pop(require_remote_url(remote), None)


__all__ = [
    "REMOTE_PORTFOLIO_SNAPSHOT_TABLES",
    "InMemoryRemotePortfolioSnapshotRepository",
    "PortfolioSnapshot",
    "RemotePortfolioSnapshotRepository",
    "SQLiteRemotePortfolioSnapshotRepository",
    "SqlRemotePortfolioSnapshotRepository",
]

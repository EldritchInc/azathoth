"""Tests that the last portfolio read from each remote is kept, in either database (ADR 0125)."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from azathoth.persistence import Database
from azathoth.remote import (
    REMOTE_PORTFOLIO_SNAPSHOT_TABLES,
    InMemoryRemotePortfolioSnapshotRepository,
    PortfolioRecord,
    PortfolioResponse,
    PortfolioSnapshot,
    RemotePortfolioSnapshotRepository,
    SqlRemotePortfolioSnapshotRepository,
)
from azathoth.sensitivity import PRIVATE_DATA_POLICY

START = datetime(2026, 11, 11, 21, 0, tzinfo=UTC)

TEAM = "https://azathoth.example.com"

OTHER = "https://other.example.com"

FIRST = PortfolioResponse(
    entries=(PortfolioRecord(identifier="openrouter/example/frontier"),),
)

SECOND = PortfolioResponse(
    entries=(
        PortfolioRecord(identifier="openrouter/example/frontier"),
        PortfolioRecord(identifier="bedrock/example/private", data_policy=PRIVATE_DATA_POLICY),
    ),
)


def clock() -> Callable[[], datetime]:
    """Return a clock a minute later each time it is read."""

    minutes: Iterator[int] = count()

    return lambda: START + timedelta(minutes=next(minutes))


@pytest.fixture(params=["sql", "memory"])
def snapshots(
    request: pytest.FixtureRequest,
    database: Database,
) -> RemotePortfolioSnapshotRepository:
    """Open the snapshot repository over an initialized database, or in memory."""

    if request.param == "memory":
        return InMemoryRemotePortfolioSnapshotRepository(clock=clock())

    database.initialize(REMOTE_PORTFOLIO_SNAPSHOT_TABLES)

    return SqlRemotePortfolioSnapshotRepository(database, clock=clock())


def test_a_portfolio_read_is_kept_with_when_it_was_read(
    snapshots: RemotePortfolioSnapshotRepository,
) -> None:
    saved = snapshots.save(f"{TEAM}/", FIRST)

    assert saved == PortfolioSnapshot(remote=TEAM, synced_at=START, portfolio=FIRST)
    assert snapshots.get(TEAM) == saved
    assert snapshots.get(f"{TEAM}/") == saved


def test_each_read_replaces_the_last(
    snapshots: RemotePortfolioSnapshotRepository,
) -> None:
    snapshots.save(TEAM, FIRST)
    snapshots.save(TEAM, SECOND)

    assert snapshots.get(TEAM) == PortfolioSnapshot(
        remote=TEAM,
        synced_at=START + timedelta(minutes=1),
        portfolio=SECOND,
    )


def test_each_remote_has_its_own_snapshot(
    snapshots: RemotePortfolioSnapshotRepository,
) -> None:
    snapshots.save(TEAM, FIRST)
    snapshots.save(OTHER, SECOND)

    team = snapshots.get(TEAM)
    other = snapshots.get(OTHER)

    assert team is not None and team.portfolio == FIRST
    assert other is not None and other.portfolio == SECOND


def test_a_remote_never_read_has_no_snapshot_and_one_forgotten_has_none(
    snapshots: RemotePortfolioSnapshotRepository,
) -> None:
    assert snapshots.get(TEAM) is None

    snapshots.save(TEAM, FIRST)
    snapshots.save(OTHER, FIRST)
    snapshots.delete(f"{TEAM}/")
    snapshots.delete(TEAM)

    assert snapshots.get(TEAM) is None
    assert snapshots.get(OTHER) is not None


def test_an_empty_portfolio_is_kept_as_empty(
    snapshots: RemotePortfolioSnapshotRepository,
) -> None:
    snapshots.save(TEAM, PortfolioResponse())

    kept = snapshots.get(TEAM)

    assert kept is not None
    assert kept.portfolio == PortfolioResponse()


@pytest.mark.parametrize("action", ["save", "get", "delete"])
def test_a_remote_that_is_not_a_url_is_refused(
    snapshots: RemotePortfolioSnapshotRepository,
    action: str,
) -> None:
    with pytest.raises(ValueError) as caught:
        if action == "save":
            snapshots.save("azathoth.example.com", FIRST)
        elif action == "get":
            snapshots.get("azathoth.example.com")
        else:
            snapshots.delete("azathoth.example.com")

    assert str(caught.value) == "Remote URL 'azathoth.example.com' is not an http or https URL."

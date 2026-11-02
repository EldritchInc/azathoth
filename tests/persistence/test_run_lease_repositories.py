"""Contract tests every run lease repository meets, in memory, SQLite and PostgreSQL."""

import threading
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from azathoth.persistence import Database, PostgresDatabase, SQLiteDatabase
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import (
    RUN_LEASE_TABLES,
    InMemoryRunLeaseRepository,
    RunLeaseHeldError,
    RunLeaseLostError,
    RunLeaseRepository,
    SqlRunLeaseRepository,
)
from tests.persistence.conftest import BACKENDS
from tests.workflows.test_run_lease import MINUTE, NOW, RUN_ID, lease

LATER = NOW + timedelta(seconds=61)


@pytest.fixture(params=("memory", *BACKENDS))
def leases(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[RunLeaseRepository]:
    """Return an empty repository of each kind in turn, over each database."""

    if request.param == "memory":
        yield InMemoryRunLeaseRepository()
        return

    database: Database = (
        SQLiteDatabase(tmp_path / "azathoth.db")
        if request.param == "sqlite"
        else request.getfixturevalue("postgres_database")
    )

    database.initialize(RUN_LEASE_TABLES)

    yield SqlRunLeaseRepository(database)


def test_an_unleased_run_has_no_lease(
    leases: RunLeaseRepository,
) -> None:
    assert leases.get(RUN_ID) is None


def test_acquiring_a_free_run_leases_it_from_now(
    leases: RunLeaseRepository,
) -> None:
    acquired = leases.acquire(RUN_ID, holder="holder-1", now=NOW, duration=MINUTE)

    assert acquired == lease()
    assert leases.get(RUN_ID) == lease()


def test_a_live_lease_refuses_another_holder_and_is_unchanged(
    leases: RunLeaseRepository,
) -> None:
    leases.acquire(RUN_ID, holder="holder-1", now=NOW, duration=MINUTE)

    with pytest.raises(RunLeaseHeldError) as error:
        leases.acquire(RUN_ID, holder="holder-2", now=NOW + timedelta(seconds=59), duration=MINUTE)

    assert error.value.lease == lease()
    assert leases.get(RUN_ID) == lease()


def test_a_holder_may_acquire_its_own_lease_again(
    leases: RunLeaseRepository,
) -> None:
    leases.acquire(RUN_ID, holder="holder-1", now=NOW, duration=MINUTE)

    again = leases.acquire(
        RUN_ID, holder="holder-1", now=NOW + timedelta(seconds=30), duration=MINUTE
    )

    assert again == lease(acquired_at=NOW + timedelta(seconds=30))


def test_a_lapsed_lease_is_taken_over(
    leases: RunLeaseRepository,
) -> None:
    leases.acquire(RUN_ID, holder="holder-1", now=NOW, duration=MINUTE)

    taken = leases.acquire(RUN_ID, holder="holder-2", now=LATER, duration=MINUTE)

    assert taken == lease(holder="holder-2", acquired_at=LATER)
    assert leases.get(RUN_ID) == taken


def test_renewing_moves_only_the_expiry(
    leases: RunLeaseRepository,
) -> None:
    leases.acquire(RUN_ID, holder="holder-1", now=NOW, duration=MINUTE)

    renewed = leases.renew(
        RUN_ID, holder="holder-1", now=NOW + timedelta(seconds=15), duration=MINUTE
    )

    assert renewed == lease(duration=timedelta(seconds=75))
    assert leases.get(RUN_ID) == renewed


@pytest.mark.parametrize("taken", [True, False], ids=["taken-over", "never-held"])
def test_a_lease_another_holds_or_none_holds_cannot_be_renewed(
    leases: RunLeaseRepository,
    taken: bool,
) -> None:
    if taken:
        leases.acquire(RUN_ID, holder="holder-1", now=NOW, duration=MINUTE)
        leases.acquire(RUN_ID, holder="holder-2", now=LATER, duration=MINUTE)

    with pytest.raises(RunLeaseLostError) as error:
        leases.renew(RUN_ID, holder="holder-1", now=LATER, duration=MINUTE)

    assert str(error.value) == f"Run {RUN_ID} was taken over by another process."


def test_releasing_removes_only_the_holders_own_lease(
    leases: RunLeaseRepository,
) -> None:
    leases.acquire(RUN_ID, holder="holder-1", now=NOW, duration=MINUTE)

    leases.release(RUN_ID, holder="holder-2")

    assert leases.get(RUN_ID) == lease()

    leases.release(RUN_ID, holder="holder-1")

    assert leases.get(RUN_ID) is None

    leases.release(RUN_ID, holder="holder-1")


def test_the_repositories_lease_runs_in_the_database_they_open(
    tmp_path: Path,
) -> None:
    repositories = open_repositories(tmp_path / "azathoth.db")

    repositories.run_leases.acquire(RUN_ID, holder="holder-1", now=NOW, duration=MINUTE)

    assert isinstance(repositories.run_leases, SqlRunLeaseRepository)
    assert open_repositories(tmp_path / "azathoth.db").run_leases.get(RUN_ID) == lease()


# Racing for one lease


def race(
    repositories: list[RunLeaseRepository],
) -> list[str]:
    """Have each repository's process try to lease the run at once; return the winners."""

    start = threading.Barrier(len(repositories))
    winners: list[str] = []
    failures: list[BaseException] = []

    def contend(index: int, repository: RunLeaseRepository) -> None:
        start.wait()

        try:
            repository.acquire(RUN_ID, holder=f"holder-{index}", now=NOW, duration=MINUTE)
        except RunLeaseHeldError:
            return
        except BaseException as error:
            failures.append(error)
            return

        winners.append(f"holder-{index}")

    threads = [
        threading.Thread(target=contend, args=(index, repository))
        for index, repository in enumerate(repositories)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert failures == []

    return winners


def test_exactly_one_of_many_racing_sqlite_processes_holds_the_lease(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    SQLiteDatabase(path).initialize(RUN_LEASE_TABLES)

    winners = race([SqlRunLeaseRepository(SQLiteDatabase(path)) for _ in range(6)])

    assert len(winners) == 1
    assert SqlRunLeaseRepository(SQLiteDatabase(path)).get(RUN_ID) == lease(holder=winners[0])


def test_exactly_one_of_many_racing_postgresql_processes_holds_the_lease(
    postgres_url: str,
) -> None:
    databases = [PostgresDatabase(postgres_url) for _ in range(6)]

    try:
        databases[0].initialize(RUN_LEASE_TABLES)

        winners = race([SqlRunLeaseRepository(database) for database in databases])

        assert len(winners) == 1
        assert SqlRunLeaseRepository(databases[0]).get(RUN_ID) == lease(holder=winners[0])
    finally:
        for database in databases:
            database.close()

"""Tests of run leases and the keeper that holds one while a run executes (ADR 0105)."""

import os
import socket
import threading
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    LEASE_DURATION,
    LEASE_RENEWAL_INTERVAL,
    InMemoryRunLeaseRepository,
    RunJournalError,
    RunLease,
    RunLeaseHeldError,
    RunLeaseKeeper,
    RunLeaseLostError,
    RunLeasePolicy,
    lease_holder,
)

RUN_ID = UUID("c1400000-0000-4000-8000-000000000001")

NOW = datetime(2026, 11, 1, 21, 30, tzinfo=UTC)

MINUTE = timedelta(seconds=60)


class Clock:
    """A clock the test moves by hand."""

    def __init__(
        self,
        now: datetime = NOW,
    ) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(
        self,
        seconds: float,
    ) -> None:
        self.now += timedelta(seconds=seconds)


def lease(
    *,
    holder: str = "holder-1",
    acquired_at: datetime = NOW,
    duration: timedelta = MINUTE,
) -> RunLease:
    """Return a lease on the test run."""

    return RunLease(
        run_id=RUN_ID,
        holder=holder,
        acquired_at=acquired_at,
        expires_at=acquired_at + duration,
    )


# Leases


def test_the_defaults_are_a_minute_renewed_every_fifteen_seconds() -> None:
    assert timedelta(seconds=60) == LEASE_DURATION
    assert timedelta(seconds=15) == LEASE_RENEWAL_INTERVAL
    assert RunLeasePolicy() == RunLeasePolicy(
        duration=LEASE_DURATION,
        renewal_interval=LEASE_RENEWAL_INTERVAL,
    )


def test_a_lease_expires_at_its_expiry_and_not_before() -> None:
    held = lease()

    assert not held.expired(NOW + timedelta(seconds=59))
    assert held.expired(NOW + MINUTE)


def test_a_lease_must_expire_after_it_is_acquired() -> None:
    with pytest.raises(ValidationError, match="A lease must expire after it is acquired."):
        lease(duration=timedelta(0))


def test_a_live_lease_names_its_run_and_when_it_expires() -> None:
    error = RunLeaseHeldError(lease())

    assert str(error) == (
        f"Run {RUN_ID} is still running (its lease expires at 2026-11-01T21:31:00+00:00)."
    )
    assert error.lease == lease()


def test_a_lease_shown_in_another_zone_is_shown_in_utc() -> None:
    eastern = NOW.astimezone(timezone(timedelta(hours=-5)))

    assert "2026-11-01T21:31:00+00:00" in str(RunLeaseHeldError(lease(acquired_at=eastern)))


def test_a_lost_lease_says_how_it_was_lost() -> None:
    assert str(RunLeaseLostError.taken_over(RUN_ID)) == (
        f"Run {RUN_ID} was taken over by another process."
    )
    assert str(RunLeaseLostError.lapsed(RUN_ID, NOW)) == (
        f"Run {RUN_ID}'s lease expired at 2026-11-01T21:30:00+00:00 before it could be renewed."
    )
    assert RunLeaseLostError.taken_over(RUN_ID).run_id == RUN_ID


def test_a_lost_lease_stops_a_run_as_a_journal_error_does() -> None:
    assert issubclass(RunLeaseLostError, RunJournalError)


@pytest.mark.parametrize(
    ("duration", "interval", "message"),
    [
        (MINUTE, timedelta(0), "A lease must be renewed at a positive interval."),
        (MINUTE, MINUTE, "A lease must be renewed more often than it lasts."),
    ],
)
def test_a_policy_renews_at_a_positive_interval_shorter_than_its_duration(
    duration: timedelta,
    interval: timedelta,
    message: str,
) -> None:
    with pytest.raises(ValueError) as error:
        RunLeasePolicy(duration=duration, renewal_interval=interval)

    assert str(error.value) == message


def test_a_holder_names_this_host_and_process_uniquely() -> None:
    first = lease_holder()

    host, pid, suffix = first.rsplit(":", 2)

    assert (host, pid) == (socket.gethostname(), str(os.getpid()))
    assert len(suffix) == 12
    assert lease_holder() != first


# The keeper


def keeper(
    repository: InMemoryRunLeaseRepository,
    clock: Clock,
    *,
    holder: str = "holder-1",
) -> RunLeaseKeeper:
    """Return a keeper of the test run's lease, on a clock moved by hand."""

    return RunLeaseKeeper(repository, RUN_ID, holder=holder, clock=clock)


def test_a_keeper_acquires_the_lease_under_its_holder() -> None:
    repository = InMemoryRunLeaseRepository()
    kept = keeper(repository, Clock())

    assert kept.acquire() == lease()
    assert kept.lease == lease()
    assert kept.holder == "holder-1"
    assert repository.get(RUN_ID) == lease()

    kept.check()


def test_a_keeper_is_refused_a_run_another_holds() -> None:
    repository = InMemoryRunLeaseRepository()
    clock = Clock()
    keeper(repository, clock, holder="holder-1").acquire()

    with pytest.raises(RunLeaseHeldError):
        keeper(repository, clock, holder="holder-2").acquire()


def test_renewing_moves_the_expiry_forward_from_now() -> None:
    repository = InMemoryRunLeaseRepository()
    clock = Clock()
    kept = keeper(repository, clock)
    kept.acquire()

    clock.advance(45)
    kept.renew()

    assert kept.lease == RunLease(
        run_id=RUN_ID,
        holder="holder-1",
        acquired_at=NOW,
        expires_at=NOW + timedelta(seconds=105),
    )

    clock.advance(59)
    kept.check()


def test_a_lease_taken_over_is_lost_and_never_renewed_again() -> None:
    repository = InMemoryRunLeaseRepository()
    clock = Clock()
    kept = keeper(repository, clock)
    kept.acquire()

    clock.advance(61)
    keeper(repository, clock, holder="holder-2").acquire()

    kept.renew()

    with pytest.raises(RunLeaseLostError) as error:
        kept.check()

    assert str(error.value) == f"Run {RUN_ID} was taken over by another process."
    assert repository.get(RUN_ID) == lease(
        holder="holder-2", acquired_at=NOW + timedelta(seconds=61)
    )


def test_a_lease_that_lapses_before_it_is_renewed_is_lost() -> None:
    clock = Clock()
    kept = keeper(InMemoryRunLeaseRepository(), clock)
    kept.acquire()

    clock.advance(60)

    with pytest.raises(RunLeaseLostError) as error:
        kept.check()

    assert str(error.value) == (
        f"Run {RUN_ID}'s lease expired at 2026-11-01T21:31:00+00:00 before it could be renewed."
    )


class FlakyLeases(InMemoryRunLeaseRepository):
    """Fail the next few renewals as if the database were unreachable."""

    def __init__(
        self,
        failures: int,
    ) -> None:
        super().__init__()
        self.failures = failures

    def renew(
        self,
        run_id: UUID,
        *,
        holder: str,
        now: datetime,
        duration: timedelta,
    ) -> RunLease:
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("database unreachable")

        return super().renew(run_id, holder=holder, now=now, duration=duration)


def test_a_renewal_that_fails_for_another_reason_is_tried_again() -> None:
    repository = FlakyLeases(failures=1)
    clock = Clock()
    kept = keeper(repository, clock)
    kept.acquire()

    clock.advance(15)
    kept.renew()

    assert kept.lease == lease()

    clock.advance(15)
    kept.renew()

    assert kept.lease == lease(duration=timedelta(seconds=90))
    kept.check()


def test_releasing_gives_up_only_the_keepers_own_lease() -> None:
    repository = InMemoryRunLeaseRepository()
    clock = Clock()
    kept = keeper(repository, clock)
    kept.acquire()

    clock.advance(61)
    keeper(repository, clock, holder="holder-2").acquire()
    kept.release()

    assert repository.get(RUN_ID) is not None

    keeper(repository, clock, holder="holder-2").release()

    assert repository.get(RUN_ID) is None


def test_a_keeper_is_checked_only_once_it_acquires() -> None:
    with pytest.raises(RuntimeError, match=r"^A lease keeper is checked only after it acquires\.$"):
        keeper(InMemoryRunLeaseRepository(), Clock()).check()


class CountingLeases(InMemoryRunLeaseRepository):
    """Count renewals, and signal each one."""

    def __init__(
        self,
    ) -> None:
        super().__init__()
        self.renewals = 0
        self.renewed = threading.Event()

    def renew(
        self,
        run_id: UUID,
        *,
        holder: str,
        now: datetime,
        duration: timedelta,
    ) -> RunLease:
        renewed = super().renew(run_id, holder=holder, now=now, duration=duration)
        self.renewals += 1
        self.renewed.set()

        return renewed


def test_a_started_keeper_renews_from_its_own_thread_until_stopped() -> None:
    repository = CountingLeases()
    kept = RunLeaseKeeper(
        repository,
        RUN_ID,
        policy=RunLeasePolicy(
            duration=timedelta(seconds=5),
            renewal_interval=timedelta(milliseconds=20),
        ),
    )
    kept.acquire()
    kept.start()

    try:
        assert repository.renewed.wait(timeout=5)

        names = {thread.name for thread in threading.enumerate()}

        assert f"azathoth-lease-{RUN_ID}" in names
    finally:
        kept.stop()

    renewals = repository.renewals
    time.sleep(0.1)

    assert repository.renewals == renewals
    assert f"azathoth-lease-{RUN_ID}" not in {thread.name for thread in threading.enumerate()}


def test_a_keeper_starts_once() -> None:
    kept = keeper(InMemoryRunLeaseRepository(), Clock())
    kept.acquire()
    kept.start()

    try:
        with pytest.raises(RuntimeError, match=r"^A lease keeper starts once\.$"):
            kept.start()
    finally:
        kept.stop()


def test_a_lease_taken_over_stops_the_renewals() -> None:
    repository = CountingLeases()
    clock = Clock()
    kept = RunLeaseKeeper(
        repository,
        RUN_ID,
        holder="holder-1",
        clock=clock,
        policy=RunLeasePolicy(
            duration=timedelta(seconds=5),
            renewal_interval=timedelta(milliseconds=10),
        ),
    )
    kept.acquire()

    clock.advance(10)
    keeper(repository, clock, holder="holder-2").acquire()

    kept.start()
    time.sleep(0.1)
    kept.stop()

    assert repository.renewals == 0

    with pytest.raises(RunLeaseLostError):
        kept.check()


DOCUMENTED = Path(__file__).parents[2] / "src" / "azathoth" / "workflows" / "README.md"


def test_the_readme_quotes_the_real_refusal_and_losses() -> None:
    text = DOCUMENTED.read_text(encoding="utf-8")
    shown = {
        str(RunLeaseHeldError(lease())),
        str(RunLeaseLostError.taken_over(RUN_ID)),
        str(RunLeaseLostError.lapsed(RUN_ID, NOW)),
    }

    for message in shown:
        documented = (
            message.replace(str(RUN_ID), "<RUN_ID>")
            .replace("2026-11-01T21:31:00+00:00", "<TIME>")
            .replace("2026-11-01T21:30:00+00:00", "<TIME>")
        )

        assert f"\n{documented}\n" in text, documented

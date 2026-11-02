"""Tests that the runner holds each run's lease while it executes (ADR 0105)."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from azathoth.context import Context, active_step_lineage
from azathoth.strategies import StrategyMetadata, StrategyOutcome
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    InMemoryRunLeaseRepository,
    RunJournalEntry,
    RunJournalError,
    RunLease,
    RunLeaseLostError,
    RunLeasePolicy,
    WorkflowRunner,
)
from tests.workflows.test_runner_journal import (
    FIRST_STEP_ID,
    INITIAL_CONTEXT,
    LATER_STEP_ID,
    FailingJournal,
    FlakyStrategy,
    candidate,
    step,
)

FAST = RunLeasePolicy(
    duration=timedelta(milliseconds=400),
    renewal_interval=timedelta(milliseconds=50),
)


class LeaseWatcher:
    """A step that records the lease on its own run while it executes."""

    def __init__(
        self,
        leases: InMemoryRunLeaseRepository,
        *,
        seconds: float = 0.0,
        during: Callable[[UUID], None] | None = None,
    ) -> None:
        self._leases = leases
        self._seconds = seconds
        self._during = during
        self.seen: list[RunLease | None] = []

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return StrategyMetadata(
            id=UUID("c1500000-0000-4000-8000-000000000021"),
            name="Lease watcher",
            description="Record the run's lease.",
            version="1.0.0",
        )

    async def run(self, context: Context) -> StrategyOutcome:
        """Record the lease, optionally wait, and record it again."""

        lineage = active_step_lineage()

        assert lineage is not None

        run_id = lineage.step.run_id

        self.seen.append(self._leases.get(run_id))

        if self._during is not None:
            self._during(run_id)

        if self._seconds:
            await asyncio.sleep(self._seconds)

        self.seen.append(self._leases.get(run_id))

        return StrategyOutcome(output="watched")


def test_a_runner_that_leases_must_journal() -> None:
    with pytest.raises(ValueError) as error:
        WorkflowRunner(leases=InMemoryRunLeaseRepository())

    assert str(error.value) == "A runner that leases its runs must journal them."


def test_a_run_holds_its_lease_while_it_executes_and_releases_it_after() -> None:
    leases = InMemoryRunLeaseRepository()
    watcher = LeaseWatcher(leases)

    run = asyncio.run(
        WorkflowRunner(journal=InMemoryRunJournalRepository(), leases=leases).run(
            candidate(step(FIRST_STEP_ID, watcher)),
            INITIAL_CONTEXT,
        )
    )

    (held, _) = watcher.seen

    assert held is not None
    assert held.run_id == run.id
    assert held.expires_at - held.acquired_at == timedelta(seconds=60)
    assert leases.get(run.id) is None


class OrderedLeases(InMemoryRunLeaseRepository):
    """Record when the lease is acquired and released, beside the journal."""

    def __init__(
        self,
        order: list[str],
    ) -> None:
        super().__init__()
        self._order = order

    def acquire(
        self,
        run_id: UUID,
        *,
        holder: str,
        now: datetime,
        duration: timedelta,
    ) -> RunLease:
        self._order.append("lease.acquired")
        return super().acquire(run_id, holder=holder, now=now, duration=duration)

    def release(
        self,
        run_id: UUID,
        *,
        holder: str,
    ) -> None:
        self._order.append("lease.released")
        super().release(run_id, holder=holder)


class OrderedJournal(InMemoryRunJournalRepository):
    """Record each entry's type beside the lease."""

    def __init__(
        self,
        order: list[str],
    ) -> None:
        super().__init__()
        self._order = order

    def append(
        self,
        entry: RunJournalEntry,
    ) -> None:
        self._order.append(entry.event.type)
        super().append(entry)


def test_the_lease_is_acquired_before_the_first_entry_and_released_after_the_last() -> None:
    order: list[str] = []

    asyncio.run(
        WorkflowRunner(journal=OrderedJournal(order), leases=OrderedLeases(order)).run(
            candidate(step(FIRST_STEP_ID, FlakyStrategy())),
            INITIAL_CONTEXT,
        )
    )

    assert order[0] == "lease.acquired"
    assert order[1] == "run.started"
    assert order[-2:] == ["run.finished", "lease.released"]


def test_a_halted_run_releases_its_lease() -> None:
    leases = OrderedLeases([])

    run = asyncio.run(
        WorkflowRunner(
            journal=InMemoryRunJournalRepository(), leases=leases
        ).run_recording_failures(
            candidate(step(FIRST_STEP_ID, FlakyStrategy(always_fail=True))),
            INITIAL_CONTEXT,
        )
    )

    assert run.halted
    assert leases.get(run.id) is None


def test_a_run_stopped_by_its_journal_releases_its_lease() -> None:
    order: list[str] = []

    with pytest.raises(RunJournalError):
        asyncio.run(
            WorkflowRunner(
                journal=FailingJournal("layer.committed"),
                leases=OrderedLeases(order),
            ).run(candidate(step(FIRST_STEP_ID, FlakyStrategy())), INITIAL_CONTEXT)
        )

    assert order == ["lease.acquired", "lease.released"]


def test_a_cancelled_run_releases_its_lease() -> None:
    leases = InMemoryRunLeaseRepository()
    watcher = LeaseWatcher(leases, seconds=30)

    async def cancel_while_running() -> None:
        task = asyncio.create_task(
            WorkflowRunner(journal=InMemoryRunJournalRepository(), leases=leases).run(
                candidate(step(FIRST_STEP_ID, watcher)),
                INITIAL_CONTEXT,
            )
        )

        while not watcher.seen:
            await asyncio.sleep(0.01)

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_while_running())

    (held,) = watcher.seen

    assert held is not None
    assert leases.get(held.run_id) is None


def test_a_long_step_keeps_its_lease_renewed() -> None:
    leases = InMemoryRunLeaseRepository()
    watcher = LeaseWatcher(leases, seconds=1.0)

    run = asyncio.run(
        WorkflowRunner(
            journal=InMemoryRunJournalRepository(),
            leases=leases,
            lease_policy=FAST,
        ).run(candidate(step(FIRST_STEP_ID, watcher)), INITIAL_CONTEXT)
    )

    before, after = watcher.seen

    assert before is not None and after is not None
    assert after.expires_at > before.expires_at + timedelta(milliseconds=500)
    assert run.succeeded


def test_a_run_taken_over_stops_before_its_next_entry() -> None:
    leases = InMemoryRunLeaseRepository()
    journal = InMemoryRunJournalRepository()

    def take_over(run_id: UUID) -> None:
        held = leases.get(run_id)

        assert held is not None

        leases.acquire(
            run_id,
            holder="another-process",
            now=held.expires_at,
            duration=timedelta(seconds=60),
        )

    watcher = LeaseWatcher(leases, seconds=0.3, during=take_over)
    later = FlakyStrategy()

    with pytest.raises(RunLeaseLostError) as error:
        asyncio.run(
            WorkflowRunner(journal=journal, leases=leases, lease_policy=FAST).run(
                candidate(
                    step(FIRST_STEP_ID, watcher),
                    step(LATER_STEP_ID, later, depends_on=(FIRST_STEP_ID,)),
                ),
                INITIAL_CONTEXT,
            )
        )

    run_id = error.value.run_id

    assert str(error.value) == f"Run {run_id} was taken over by another process."
    assert [entry.event.type for entry in journal.entries(run_id)] == [
        "run.started",
        "attempt.started",
    ]
    assert later.calls == 0

    #
    # The process that took the run over keeps its lease.
    #
    taken = leases.get(run_id)

    assert taken is not None
    assert taken.holder == "another-process"


class UnreachableRenewals(InMemoryRunLeaseRepository):
    """Acquire normally, then fail every renewal as if the database were gone."""

    def renew(
        self,
        run_id: UUID,
        *,
        holder: str,
        now: datetime,
        duration: timedelta,
    ) -> RunLease:
        raise ConnectionError("database unreachable")


def test_a_run_whose_lease_lapses_unrenewed_stops_before_its_next_entry() -> None:
    leases = UnreachableRenewals()
    journal = InMemoryRunJournalRepository()

    with pytest.raises(RunLeaseLostError) as error:
        asyncio.run(
            WorkflowRunner(journal=journal, leases=leases, lease_policy=FAST).run(
                candidate(step(FIRST_STEP_ID, LeaseWatcher(leases, seconds=0.6))),
                INITIAL_CONTEXT,
            )
        )

    assert "lease expired at" in str(error.value)
    assert str(error.value).endswith("before it could be renewed.")
    assert [entry.event.type for entry in journal.entries(error.value.run_id)] == [
        "run.started",
        "attempt.started",
    ]


class UnreleasableLeases(InMemoryRunLeaseRepository):
    """Fail to release, as if the database went away at the end."""

    def release(
        self,
        run_id: UUID,
        *,
        holder: str,
    ) -> None:
        raise ConnectionError("database unreachable")


def test_a_lease_that_cannot_be_released_does_not_cost_the_run_its_result() -> None:
    leases = UnreleasableLeases()

    run = asyncio.run(
        WorkflowRunner(journal=InMemoryRunJournalRepository(), leases=leases).run(
            candidate(step(FIRST_STEP_ID, FlakyStrategy())),
            INITIAL_CONTEXT,
        )
    )

    assert run.succeeded

    remaining = leases.get(run.id)

    assert remaining is not None
    assert remaining.expires_at - remaining.acquired_at == timedelta(seconds=60)

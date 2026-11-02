"""The lease a process holds on a run while it executes it (ADR 0105).

A run that is journaled is also leased: one process holds it, until a time
it keeps moving forward. A lease that lapses, because its process was
killed or lost its database, may be taken by another process, which can
then resume the run. A live lease refuses that:

```text
Run <RUN_ID> is still running (its lease expires at <TIME>).
```

A `RunLeaseKeeper` acquires a run's lease, renews it from a thread of its
own, and releases it. Its `check` is the journal's fence: once the lease is
lost, by being taken over or by lapsing before it could be renewed, the
process writes nothing more to the run's journal.
"""

import os
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol, TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from azathoth.workflows.run_journal import RunJournalError

LEASE_DURATION: Final = timedelta(seconds=60)
"""How long a lease lasts from when it was last acquired or renewed."""

LEASE_RENEWAL_INTERVAL: Final = timedelta(seconds=15)
"""How often a keeper renews the lease it holds."""


def _timestamp(
    moment: datetime,
) -> str:
    """Return a moment as messages show it: UTC, to the second."""

    return moment.astimezone(UTC).isoformat(timespec="seconds")


class RunLease(BaseModel):
    """The lease one process holds on one run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    holder: str
    acquired_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_period(self) -> "RunLease":
        """Ensure a lease expires after it was acquired."""

        if self.expires_at <= self.acquired_at:
            raise ValueError("A lease must expire after it is acquired.")

        return self

    def expired(
        self,
        now: datetime,
    ) -> bool:
        """Return whether the lease has lapsed by the given moment."""

        return self.expires_at <= now


class RunLeaseError(RuntimeError):
    """A run's lease could not be acquired."""


class RunLeaseHeldError(RunLeaseError):
    """Another process holds a live lease on the run."""

    def __init__(
        self,
        lease: RunLease,
    ) -> None:
        super().__init__(
            f"Run {lease.run_id} is still running "
            f"(its lease expires at {_timestamp(lease.expires_at)})."
        )
        self.lease = lease


class RunLeaseLostError(RunJournalError):
    """This process no longer holds the run, so it must not journal it.

    It is a journal error: the runner stops at once with it, as it does
    when an entry cannot be recorded.
    """

    def __init__(
        self,
        run_id: UUID,
        message: str,
    ) -> None:
        super().__init__(message)
        self.run_id = run_id

    @classmethod
    def taken_over(
        cls,
        run_id: UUID,
    ) -> "RunLeaseLostError":
        """Return the error for a lease another process now holds."""

        return cls(run_id, f"Run {run_id} was taken over by another process.")

    @classmethod
    def lapsed(
        cls,
        run_id: UUID,
        expires_at: datetime,
    ) -> "RunLeaseLostError":
        """Return the error for a lease that lapsed before it was renewed."""

        return cls(
            run_id,
            f"Run {run_id}'s lease expired at {_timestamp(expires_at)} before it could be renewed.",
        )


class RunLeaseRepository(Protocol):
    """Persist the leases on runs, one per run."""

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

        ...

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

        ...

    def release(
        self,
        run_id: UUID,
        *,
        holder: str,
    ) -> None:
        """Release the holder's lease, if it still holds it."""

        ...

    def get(
        self,
        run_id: UUID,
    ) -> RunLease | None:
        """Return the run's lease, live or lapsed, if one is recorded."""

        ...


class InMemoryRunLeaseRepository:
    """Keep run leases in memory, for tests and short-lived processes."""

    def __init__(
        self,
    ) -> None:
        self._leases: dict[UUID, RunLease] = {}
        self._lock = threading.Lock()

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
            RunLeaseHeldError: Another holder's lease is live.
        """

        with self._lock:
            existing = self._leases.get(run_id)

            if existing is not None and existing.holder != holder and not existing.expired(now):
                raise RunLeaseHeldError(existing)

            lease = RunLease(
                run_id=run_id,
                holder=holder,
                acquired_at=now,
                expires_at=now + duration,
            )
            self._leases[run_id] = lease

            return lease

    def renew(
        self,
        run_id: UUID,
        *,
        holder: str,
        now: datetime,
        duration: timedelta,
    ) -> RunLease:
        """Move the holder's lease forward.

        Raises:
            RunLeaseLostError: The holder no longer holds the run's lease.
        """

        with self._lock:
            existing = self._leases.get(run_id)

            if existing is None or existing.holder != holder:
                raise RunLeaseLostError.taken_over(run_id)

            lease = existing.model_copy(update={"expires_at": now + duration})
            self._leases[run_id] = lease

            return lease

    def release(
        self,
        run_id: UUID,
        *,
        holder: str,
    ) -> None:
        """Release the holder's lease, if it still holds it."""

        with self._lock:
            existing = self._leases.get(run_id)

            if existing is not None and existing.holder == holder:
                del self._leases[run_id]

    def get(
        self,
        run_id: UUID,
    ) -> RunLease | None:
        """Return the run's lease, if one is recorded."""

        with self._lock:
            return self._leases.get(run_id)


@dataclass(frozen=True)
class RunLeasePolicy:
    """How long a lease lasts, and how often its keeper renews it."""

    duration: timedelta = LEASE_DURATION
    renewal_interval: timedelta = LEASE_RENEWAL_INTERVAL

    def __post_init__(
        self,
    ) -> None:
        if self.renewal_interval <= timedelta(0):
            raise ValueError("A lease must be renewed at a positive interval.")

        if self.renewal_interval >= self.duration:
            raise ValueError("A lease must be renewed more often than it lasts.")


Clock: TypeAlias = Callable[[], datetime]
"""Return the current time."""


def _now() -> datetime:
    """Return the current time in UTC."""

    return datetime.now(UTC)


def lease_holder() -> str:
    """Return a name for a new holder: this host and process, and a unique suffix."""

    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:12]}"


class RunLeaseKeeper:
    """Hold one run's lease for as long as this process executes the run.

    `acquire` takes the lease; `start` renews it from a daemon thread at the
    policy's interval; `stop` ends the renewals; `release` gives it up.
    `check` raises once the lease is lost.
    """

    def __init__(
        self,
        repository: RunLeaseRepository,
        run_id: UUID,
        *,
        holder: str | None = None,
        policy: RunLeasePolicy | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._run_id = run_id
        self._holder = holder if holder is not None else lease_holder()
        self._policy = policy if policy is not None else RunLeasePolicy()
        self._clock: Clock = clock if clock is not None else _now
        self._lease: RunLease | None = None
        self._lost: RunLeaseLostError | None = None
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = threading.Lock()

    @property
    def holder(
        self,
    ) -> str:
        """Return the name this keeper holds the lease under."""

        return self._holder

    @property
    def lease(
        self,
    ) -> RunLease | None:
        """Return the lease as last acquired or renewed."""

        with self._state:
            return self._lease

    def acquire(
        self,
    ) -> RunLease:
        """Acquire the run's lease.

        Raises:
            RunLeaseHeldError: Another process holds a live lease on the run.
        """

        lease = self._repository.acquire(
            self._run_id,
            holder=self._holder,
            now=self._clock(),
            duration=self._policy.duration,
        )

        with self._state:
            self._lease = lease

        return lease

    def renew(
        self,
    ) -> None:
        """Renew the lease once, recording a loss instead of raising it."""

        try:
            lease = self._repository.renew(
                self._run_id,
                holder=self._holder,
                now=self._clock(),
                duration=self._policy.duration,
            )
        except RunLeaseLostError as error:
            with self._state:
                self._lost = error

            self._stopped.set()

            return
        except Exception:
            #
            # A renewal that fails for any other reason, such as a database
            # that is briefly unreachable, is tried again at the next
            # interval. `check` refuses once the lease has lapsed.
            #
            return

        with self._state:
            self._lease = lease

    def start(
        self,
    ) -> None:
        """Renew the lease from a daemon thread until stopped."""

        if self._thread is not None:
            raise RuntimeError("A lease keeper starts once.")

        interval = self._policy.renewal_interval.total_seconds()

        def keep() -> None:
            while not self._stopped.wait(interval):
                self.renew()

        self._thread = threading.Thread(
            target=keep,
            name=f"azathoth-lease-{self._run_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(
        self,
    ) -> None:
        """Stop renewing, waiting for a renewal in progress to finish."""

        self._stopped.set()

        if self._thread is not None:
            self._thread.join()

    def release(
        self,
    ) -> None:
        """Release the lease, if this keeper still holds it."""

        self._repository.release(self._run_id, holder=self._holder)

    def check(
        self,
    ) -> None:
        """Raise if this process no longer holds the run.

        Raises:
            RunLeaseLostError: The lease was taken over, or lapsed before it
                could be renewed.
        """

        with self._state:
            lost = self._lost
            lease = self._lease

        if lost is not None:
            raise lost

        if lease is None:
            raise RuntimeError("A lease keeper is checked only after it acquires.")

        if lease.expired(self._clock()):
            raise RunLeaseLostError.lapsed(self._run_id, lease.expires_at)


__all__ = [
    "LEASE_DURATION",
    "LEASE_RENEWAL_INTERVAL",
    "InMemoryRunLeaseRepository",
    "RunLease",
    "RunLeaseError",
    "RunLeaseHeldError",
    "RunLeaseKeeper",
    "RunLeaseLostError",
    "RunLeasePolicy",
    "RunLeaseRepository",
    "lease_holder",
]

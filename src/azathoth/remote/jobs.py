"""The jobs a remote runs on its runners, and the events they tell, kept in its database (ADR 0138).

A call of the service API that runs a workflow, a benchmark or an
optimization is a job: it is submitted, waits in `service_jobs` until a
runner claims it, and tells its events into `service_job_events` as it runs,
so a caller may follow it from another request, or from another server
over the same PostgreSQL database. Each runner keeps a row of its own in
`service_job_runners`, beating as it runs, so a job whose runner stopped
beating can be found and recovered.

A job's arguments, its result and its refusal are kept as the JSON its call
writes them as; this module reads none of them.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from azathoth.persistence import (
    Database,
    Parameter,
    Row,
    Session,
    Table,
    require_integer,
    require_text,
)

SERVICE_JOB_TABLES: Final = (
    Table(
        name="service_jobs",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                service_jobs (
                    queue_position {sequence},
                    job_id TEXT NOT NULL UNIQUE,
                    call_name TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    resource TEXT,
                    status TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    runner_id TEXT,
                    heartbeat_at TEXT,
                    cancel_requested_at TEXT,
                    cancelled_by TEXT,
                    run_id TEXT,
                    attempts INTEGER NOT NULL,
                    result TEXT,
                    refusal TEXT,
                    refusal_status INTEGER
                )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                service_jobs_by_status
                ON service_jobs (status, queue_position)
            """,
            """
            CREATE INDEX IF NOT EXISTS
                service_jobs_by_principal
                ON service_jobs (principal, queue_position)
            """,
        ),
    ),
    Table(
        name="service_job_events",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                service_job_events (
                    job_id TEXT NOT NULL REFERENCES service_jobs (job_id),
                    event_number INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, event_number)
                )
            """,
        ),
    ),
    Table(
        name="service_job_runners",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                service_job_runners (
                    runner_id TEXT NOT NULL PRIMARY KEY,
                    server TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL
                )
            """,
        ),
    ),
)
"""The tables a remote's jobs, their events and its runners are kept in (ADR 0138).

Jobs were first kept in this version, so there is nothing to backfill.
"""


class ServiceJobStatus(StrEnum):
    """Where a job is: waiting, running, or finished one of four ways."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def finished(
        self,
    ) -> bool:
        """Return whether a job of this status will never run again."""

        return self not in (ServiceJobStatus.QUEUED, ServiceJobStatus.RUNNING)


FINISHED_STATUSES: Final = frozenset(status for status in ServiceJobStatus if status.finished)
"""The statuses a job ends with."""


class ServiceJob(BaseModel):
    """One job: the call it makes, who submitted it, and how far it has got."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    job_id: UUID

    call: str = Field(
        description="The name of the call the job makes, such as `runs.run`.",
    )

    principal: str = Field(
        description="The name of the caller who submitted it, as whom it runs.",
    )

    arguments: str = Field(
        description="The call's arguments, as the JSON its call writes them as.",
    )

    resource: str | None = Field(
        default=None,
        description="The resource the call names, as the policy was asked about it.",
    )

    status: ServiceJobStatus

    submitted_at: AwareDatetime

    started_at: AwareDatetime | None = None

    finished_at: AwareDatetime | None = None

    runner_id: str | None = Field(
        default=None,
        description="The runner that holds the job while it runs, or last held it.",
    )

    heartbeat_at: AwareDatetime | None = Field(
        default=None,
        description="When the runner holding it last beat.",
    )

    cancel_requested_at: AwareDatetime | None = None

    cancelled_by: str | None = None

    run_id: UUID | None = Field(
        default=None,
        description="The run the job started, once it has started one, so it can be resumed.",
    )

    attempts: int = Field(
        default=0,
        ge=0,
        description="How many times a runner has claimed it.",
    )

    result: str | None = Field(
        default=None,
        description="The call's result, as the JSON its call writes it as, once it succeeded.",
    )

    refusal: str | None = Field(
        default=None,
        description="The refusal a remote answers its failure with, once it failed.",
    )

    refusal_status: int | None = Field(
        default=None,
        description="The HTTP status of its refusal.",
    )


class ServiceJobEvent(BaseModel):
    """One event a job told, numbered in the order it was told, from 1."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    job_id: UUID

    sequence: int = Field(
        ge=1,
    )

    event: str = Field(
        description="The event, as the JSON its call's events are written as.",
    )

    recorded_at: AwareDatetime


class ServiceJobRunner(BaseModel):
    """One runner of a remote's jobs, and when it last beat."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    runner_id: str

    server: str = Field(
        description="Which server process the runner runs in.",
    )

    started_at: AwareDatetime

    heartbeat_at: AwareDatetime


class ServiceJobSummary(BaseModel):
    """How a remote's jobs stand: how many wait, how many run, and who runs them."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    queued: int = Field(
        ge=0,
    )

    running: int = Field(
        ge=0,
    )

    runners: int = Field(
        ge=0,
        description="The runners that beat since the time asked about.",
    )

    oldest_queued_at: AwareDatetime | None = Field(
        default=None,
        description="When the job waiting longest was submitted, if any waits.",
    )


JOBS_ROUTE: Final = "/v1/jobs"
"""Where a remote answers about the jobs it runs."""


def job_path(
    job_id: UUID,
) -> str:
    """Return where a remote answers about one job."""

    return f"{JOBS_ROUTE}/{job_id}"


def events_path(
    job_id: UUID,
) -> str:
    """Return where a remote streams one job's events."""

    return f"{job_path(job_id)}/events"


class JobAccepted(BaseModel):
    """What a remote answers a job submitted with: where to follow it (ADR 0138)."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    job_id: UUID

    call: str

    status: ServiceJobStatus

    submitted_at: AwareDatetime

    job: str = Field(
        description="Where the remote answers about the job: its status, and its result.",
    )

    events: str = Field(
        description="Where the remote streams the job's events, as they are told.",
    )

    @classmethod
    def of(
        cls,
        job: ServiceJob,
    ) -> "JobAccepted":
        """Return what a remote answers the submission of a job with."""

        return cls(
            job_id=job.job_id,
            call=job.call,
            status=job.status,
            submitted_at=job.submitted_at,
            job=job_path(job.job_id),
            events=events_path(job.job_id),
        )


class ServiceJobRepository(Protocol):
    """The jobs of one remote, their events, and its runners."""

    def submit(
        self,
        job_id: UUID,
        *,
        call: str,
        principal: str,
        arguments: str,
        resource: str | None = None,
    ) -> ServiceJob:
        """Queue a job, and return it as queued."""

        ...

    def get(
        self,
        job_id: UUID,
    ) -> ServiceJob | None:
        """Return one job, or None when there is none of that ID."""

        ...

    def jobs(
        self,
        *,
        principal: str | None = None,
        limit: int = 100,
    ) -> tuple[ServiceJob, ...]:
        """Return the jobs submitted, newest first, of one caller when one is named."""

        ...

    def claim(
        self,
        runner_id: str,
    ) -> ServiceJob | None:
        """Take the job waiting longest for a runner, and return it as running."""

        ...

    def record_run(
        self,
        job_id: UUID,
        run_id: UUID,
    ) -> None:
        """Record the run a job started."""

        ...

    def append_event(
        self,
        job_id: UUID,
        event: str,
    ) -> ServiceJobEvent:
        """Record the next event a job told, and return it numbered."""

        ...

    def events(
        self,
        job_id: UUID,
        *,
        after: int = 0,
    ) -> tuple[ServiceJobEvent, ...]:
        """Return the events a job told after the one numbered `after`, in order."""

        ...

    def finish(
        self,
        job_id: UUID,
        runner_id: str,
        status: ServiceJobStatus,
        *,
        result: str | None = None,
        refusal: str | None = None,
        refusal_status: int | None = None,
    ) -> bool:
        """End a job the runner holds, and return whether it held it."""

        ...

    def request_cancel(
        self,
        job_id: UUID,
        by: str,
    ) -> ServiceJob | None:
        """Ask a job to stop, and return it as it is after asking."""

        ...

    def stalled(
        self,
        before: datetime,
    ) -> tuple[ServiceJob, ...]:
        """Return the jobs running whose runner last beat before a time."""

        ...

    def requeue(
        self,
        stalled: ServiceJob,
        *,
        call: str,
        arguments: str,
    ) -> bool:
        """Queue a stalled job again, as the call given, and return whether it was still stalled."""

        ...

    def interrupt(
        self,
        stalled: ServiceJob,
        *,
        refusal: str,
        refusal_status: int,
    ) -> bool:
        """End a stalled job as interrupted, and return whether it was still stalled."""

        ...

    def register_runner(
        self,
        runner_id: str,
        server: str,
    ) -> ServiceJobRunner:
        """Record that a runner has started, and return it."""

        ...

    def beat(
        self,
        runner_id: str,
    ) -> None:
        """Record that a runner, and every job it holds, is still alive."""

        ...

    def retire_runner(
        self,
        runner_id: str,
    ) -> None:
        """Forget a runner that has stopped."""

        ...

    def runners(
        self,
    ) -> tuple[ServiceJobRunner, ...]:
        """Return every runner recorded, oldest first."""

        ...

    def summary(
        self,
        alive_since: datetime,
    ) -> ServiceJobSummary:
        """Return how the jobs stand, counting the runners that beat since a time."""

        ...


class SqlServiceJobRepository:
    """The jobs of one remote, their events and its runners, kept in a database.

    A claim takes an exclusive write lock on `service_jobs`, so two runners,
    on one server or on several over one PostgreSQL database, never claim
    the same job. Every other change is made only while the job is as it
    was read, so a runner and a recovery never both finish one job.
    """

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._database = database
        self._clock = clock
        database.prepare(SERVICE_JOB_TABLES)

    def submit(
        self,
        job_id: UUID,
        *,
        call: str,
        principal: str,
        arguments: str,
        resource: str | None = None,
    ) -> ServiceJob:
        """Queue a job, and return it as queued.

        Raises:
            IntegrityError: A job of the ID was already submitted.
        """

        now = _stamp(self._clock())

        with self._database.transaction() as session:
            session.execute(
                """
                INSERT INTO service_jobs (
                    job_id,
                    call_name,
                    principal,
                    arguments,
                    resource,
                    status,
                    submitted_at,
                    attempts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    str(job_id),
                    call,
                    principal,
                    arguments,
                    resource,
                    ServiceJobStatus.QUEUED.value,
                    now,
                ),
            )

            return _required(session, job_id)

    def get(
        self,
        job_id: UUID,
    ) -> ServiceJob | None:
        """Return one job, or None when there is none of that ID."""

        with self._database.transaction(read_only=True) as session:
            return _job_of(session, job_id)

    def jobs(
        self,
        *,
        principal: str | None = None,
        limit: int = 100,
    ) -> tuple[ServiceJob, ...]:
        """Return at most `limit` jobs submitted, newest first, of one caller when one is named.

        Raises:
            ValueError: `limit` is below 1.
        """

        if limit < 1:
            raise ValueError("A limit of jobs must be at least 1.")

        mine = "" if principal is None else "WHERE principal = ?"
        parameters: tuple[Parameter, ...] = () if principal is None else (principal,)

        with self._database.transaction(read_only=True) as session:
            rows = session.fetchall(
                f"""
                SELECT {_JOB_COLUMNS}
                FROM service_jobs
                {mine}
                ORDER BY queue_position DESC
                LIMIT ?
                """,
                (*parameters, limit),
            )

        return tuple(_job(row) for row in rows)

    def claim(
        self,
        runner_id: str,
    ) -> ServiceJob | None:
        """Take the job waiting longest for a runner, and return it as running, or None."""

        now = _stamp(self._clock())

        with self._database.transaction(lock="service_jobs") as session:
            row = session.fetchone(
                """
                SELECT job_id
                FROM service_jobs
                WHERE status = ?
                ORDER BY queue_position
                LIMIT 1
                """,
                (ServiceJobStatus.QUEUED.value,),
            )

            if row is None:
                return None

            job_id = UUID(require_text(row[0], "A job's ID was not text."))
            session.execute(
                """
                UPDATE service_jobs
                SET status = ?,
                    started_at = ?,
                    runner_id = ?,
                    heartbeat_at = ?,
                    attempts = attempts + 1
                WHERE job_id = ?
                """,
                (ServiceJobStatus.RUNNING.value, now, runner_id, now, str(job_id)),
            )

            return _required(session, job_id)

    def record_run(
        self,
        job_id: UUID,
        run_id: UUID,
    ) -> None:
        """Record the run a job started, so a recovery resumes it."""

        with self._database.transaction() as session:
            session.execute(
                "UPDATE service_jobs SET run_id = ? WHERE job_id = ?",
                (str(run_id), str(job_id)),
            )

    def append_event(
        self,
        job_id: UUID,
        event: str,
    ) -> ServiceJobEvent:
        """Record the next event a job told, and return it numbered.

        One runner tells a job's events, so the next number is the last one's
        and one; two that raced would break the key, never share a number.

        Raises:
            IntegrityError: Another event took the number, or no job has the ID.
        """

        now = self._clock()

        with self._database.transaction() as session:
            row = session.fetchone(
                "SELECT MAX(event_number) FROM service_job_events WHERE job_id = ?",
                (str(job_id),),
            )
            last = 0 if row is None or row[0] is None else require_integer(row[0], _NOT_NUMBERED)
            session.execute(
                """
                INSERT INTO service_job_events (
                    job_id,
                    event_number,
                    event,
                    recorded_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (str(job_id), last + 1, event, _stamp(now)),
            )

        return ServiceJobEvent(job_id=job_id, sequence=last + 1, event=event, recorded_at=now)

    def events(
        self,
        job_id: UUID,
        *,
        after: int = 0,
    ) -> tuple[ServiceJobEvent, ...]:
        """Return the events a job told after the one numbered `after`, in order."""

        with self._database.transaction(read_only=True) as session:
            rows = session.fetchall(
                """
                SELECT job_id, event_number, event, recorded_at
                FROM service_job_events
                WHERE job_id = ? AND event_number > ?
                ORDER BY event_number
                """,
                (str(job_id), after),
            )

        return tuple(
            ServiceJobEvent(
                job_id=UUID(require_text(row[0], "A job's ID was not text.")),
                sequence=require_integer(row[1], _NOT_NUMBERED),
                event=require_text(row[2], "A job's event was not text."),
                recorded_at=datetime.fromisoformat(
                    require_text(row[3], "When an event was recorded was not text.")
                ),
            )
            for row in rows
        )

    def finish(
        self,
        job_id: UUID,
        runner_id: str,
        status: ServiceJobStatus,
        *,
        result: str | None = None,
        refusal: str | None = None,
        refusal_status: int | None = None,
    ) -> bool:
        """End a job the runner holds, and return whether it held it.

        A job recovered from the runner, or cancelled before it ran, is left
        as it is, and False returned.

        Raises:
            ValueError: The status is not one a job ends with.
        """

        if not status.finished:
            raise ValueError(f"A job does not end {status.value}.")

        with self._database.transaction() as session:
            changed = session.execute(
                """
                UPDATE service_jobs
                SET status = ?,
                    finished_at = ?,
                    result = ?,
                    refusal = ?,
                    refusal_status = ?
                WHERE job_id = ? AND status = ? AND runner_id = ?
                """,
                (
                    status.value,
                    _stamp(self._clock()),
                    result,
                    refusal,
                    refusal_status,
                    str(job_id),
                    ServiceJobStatus.RUNNING.value,
                    runner_id,
                ),
            )

        return changed == 1

    def request_cancel(
        self,
        job_id: UUID,
        by: str,
    ) -> ServiceJob | None:
        """Ask a job to stop, and return it as it is after asking, or None when there is none.

        A job still waiting is cancelled at once; one running is asked, and
        its runner stops it; one that has finished is left as it is.
        """

        now = _stamp(self._clock())

        with self._database.transaction(lock="service_jobs") as session:
            job = _job_of(session, job_id)

            if job is None or job.status.finished:
                return job

            if job.status is ServiceJobStatus.QUEUED:
                session.execute(
                    """
                    UPDATE service_jobs
                    SET status = ?, finished_at = ?, cancel_requested_at = ?, cancelled_by = ?
                    WHERE job_id = ?
                    """,
                    (ServiceJobStatus.CANCELLED.value, now, now, by, str(job_id)),
                )
            elif job.cancel_requested_at is None:
                session.execute(
                    """
                    UPDATE service_jobs
                    SET cancel_requested_at = ?, cancelled_by = ?
                    WHERE job_id = ?
                    """,
                    (now, by, str(job_id)),
                )

            return _required(session, job_id)

    def stalled(
        self,
        before: datetime,
    ) -> tuple[ServiceJob, ...]:
        """Return the jobs running whose runner last beat before a time, oldest first."""

        with self._database.transaction(read_only=True) as session:
            rows = session.fetchall(
                f"""
                SELECT {_JOB_COLUMNS}
                FROM service_jobs
                WHERE status = ? AND heartbeat_at < ?
                ORDER BY queue_position
                """,
                (ServiceJobStatus.RUNNING.value, _stamp(before)),
            )

        return tuple(_job(row) for row in rows)

    def requeue(
        self,
        stalled: ServiceJob,
        *,
        call: str,
        arguments: str,
    ) -> bool:
        """Queue a stalled job again, as the call given, and return whether it was still stalled.

        It keeps its place, ahead of every job submitted after it, and its
        events, which the call it is queued as goes on from.
        """

        with self._database.transaction() as session:
            changed = session.execute(
                """
                UPDATE service_jobs
                SET status = ?,
                    call_name = ?,
                    arguments = ?,
                    started_at = NULL,
                    runner_id = NULL,
                    heartbeat_at = NULL
                WHERE job_id = ? AND status = ? AND runner_id = ? AND heartbeat_at = ?
                """,
                (
                    ServiceJobStatus.QUEUED.value,
                    call,
                    arguments,
                    *_still_stalled(stalled),
                ),
            )

        return changed == 1

    def interrupt(
        self,
        stalled: ServiceJob,
        *,
        refusal: str,
        refusal_status: int,
    ) -> bool:
        """End a stalled job as interrupted, and return whether it was still stalled."""

        with self._database.transaction() as session:
            changed = session.execute(
                """
                UPDATE service_jobs
                SET status = ?,
                    finished_at = ?,
                    refusal = ?,
                    refusal_status = ?
                WHERE job_id = ? AND status = ? AND runner_id = ? AND heartbeat_at = ?
                """,
                (
                    ServiceJobStatus.INTERRUPTED.value,
                    _stamp(self._clock()),
                    refusal,
                    refusal_status,
                    *_still_stalled(stalled),
                ),
            )

        return changed == 1

    def register_runner(
        self,
        runner_id: str,
        server: str,
    ) -> ServiceJobRunner:
        """Record that a runner has started, and return it.

        Raises:
            IntegrityError: A runner of the ID is already recorded.
        """

        now = self._clock()

        with self._database.transaction() as session:
            session.execute(
                """
                INSERT INTO service_job_runners (
                    runner_id,
                    server,
                    started_at,
                    heartbeat_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (runner_id, server, _stamp(now), _stamp(now)),
            )

        return ServiceJobRunner(
            runner_id=runner_id,
            server=server,
            started_at=now,
            heartbeat_at=now,
        )

    def beat(
        self,
        runner_id: str,
    ) -> None:
        """Record that a runner, and every job it holds, is still alive."""

        now = _stamp(self._clock())

        with self._database.transaction() as session:
            session.execute(
                "UPDATE service_job_runners SET heartbeat_at = ? WHERE runner_id = ?",
                (now, runner_id),
            )
            session.execute(
                """
                UPDATE service_jobs
                SET heartbeat_at = ?
                WHERE runner_id = ? AND status = ?
                """,
                (now, runner_id, ServiceJobStatus.RUNNING.value),
            )

    def retire_runner(
        self,
        runner_id: str,
    ) -> None:
        """Forget a runner that has stopped; forgetting one never recorded changes nothing."""

        with self._database.transaction() as session:
            session.execute(
                "DELETE FROM service_job_runners WHERE runner_id = ?",
                (runner_id,),
            )

    def runners(
        self,
    ) -> tuple[ServiceJobRunner, ...]:
        """Return every runner recorded, oldest first."""

        with self._database.transaction(read_only=True) as session:
            rows = session.fetchall(
                """
                SELECT runner_id, server, started_at, heartbeat_at
                FROM service_job_runners
                ORDER BY started_at, runner_id
                """
            )

        return tuple(
            ServiceJobRunner(
                runner_id=require_text(row[0], "A runner's ID was not text."),
                server=require_text(row[1], "A runner's server was not text."),
                started_at=_moment(row[2]),
                heartbeat_at=_moment(row[3]),
            )
            for row in rows
        )

    def summary(
        self,
        alive_since: datetime,
    ) -> ServiceJobSummary:
        """Return how the jobs stand, counting the runners that beat since a time."""

        with self._database.transaction(read_only=True) as session:
            counts = dict(
                (
                    require_text(row[0], "A job's status was not text."),
                    require_integer(row[1], "A count of jobs was not an integer."),
                )
                for row in session.fetchall(
                    """
                    SELECT status, COUNT(*)
                    FROM service_jobs
                    WHERE status IN (?, ?)
                    GROUP BY status
                    """,
                    (ServiceJobStatus.QUEUED.value, ServiceJobStatus.RUNNING.value),
                )
            )
            oldest = session.fetchone(
                """
                SELECT submitted_at
                FROM service_jobs
                WHERE status = ?
                ORDER BY queue_position
                LIMIT 1
                """,
                (ServiceJobStatus.QUEUED.value,),
            )
            alive = session.fetchone(
                "SELECT COUNT(*) FROM service_job_runners WHERE heartbeat_at >= ?",
                (_stamp(alive_since),),
            )

        return ServiceJobSummary(
            queued=counts.get(ServiceJobStatus.QUEUED.value, 0),
            running=counts.get(ServiceJobStatus.RUNNING.value, 0),
            runners=0 if alive is None else require_integer(alive[0], _NOT_COUNTED),
            oldest_queued_at=None if oldest is None else _moment(oldest[0]),
        )


_NOT_NUMBERED: Final = "An event's number was not an integer."

STAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%S.%f+00:00"
"""How a moment is kept: in UTC, always with microseconds, so moments compare as text."""

_NOT_COUNTED: Final = "A count of runners was not an integer."

_JOB_COLUMNS: Final = (
    "job_id, call_name, principal, arguments, resource, status, submitted_at, started_at, "
    "finished_at, runner_id, heartbeat_at, cancel_requested_at, cancelled_by, run_id, attempts, "
    "result, refusal, refusal_status"
)
"""The columns a job is read from, in the order `_job` reads them."""


def _still_stalled(
    stalled: ServiceJob,
) -> tuple[Parameter, ...]:
    """Return the parameters that match a stalled job only while it is as it was read."""

    assert stalled.heartbeat_at is not None, "A stalled job has a heartbeat."

    return (
        str(stalled.job_id),
        ServiceJobStatus.RUNNING.value,
        stalled.runner_id,
        _stamp(stalled.heartbeat_at),
    )


def _job_of(
    session: Session,
    job_id: UUID,
) -> ServiceJob | None:
    """Return one job as a transaction sees it, or None."""

    row = session.fetchone(
        f"SELECT {_JOB_COLUMNS} FROM service_jobs WHERE job_id = ?",
        (str(job_id),),
    )

    return None if row is None else _job(row)


def _required(
    session: Session,
    job_id: UUID,
) -> ServiceJob:
    """Return a job the transaction has just written."""

    job = _job_of(session, job_id)
    assert job is not None, "A job just written is there."

    return job


def _stamp(
    moment: datetime,
) -> str:
    """Return a moment as it is kept, in UTC with microseconds."""

    return moment.astimezone(UTC).strftime(STAMP_FORMAT)


def _moment(
    value: object,
) -> datetime:
    """Return the moment a column holds."""

    return datetime.fromisoformat(require_text(value, "A moment was not text."))


def _optional_moment(
    value: object,
) -> datetime | None:
    """Return the moment a column holds, or None when it holds none."""

    return None if value is None else _moment(value)


def _optional_text(
    value: object,
    message: str,
) -> str | None:
    """Return the text a column holds, or None when it holds none."""

    return None if value is None else require_text(value, message)


def _job(
    row: Row,
) -> ServiceJob:
    """Return the job one row holds."""

    run_id = _optional_text(row[13], "A job's run was not text.")
    refusal_status = row[17]

    return ServiceJob(
        job_id=UUID(require_text(row[0], "A job's ID was not text.")),
        call=require_text(row[1], "A job's call was not text."),
        principal=require_text(row[2], "A job's caller was not text."),
        arguments=require_text(row[3], "A job's arguments were not text."),
        resource=_optional_text(row[4], "A job's resource was not text."),
        status=ServiceJobStatus(require_text(row[5], "A job's status was not text.")),
        submitted_at=_moment(row[6]),
        started_at=_optional_moment(row[7]),
        finished_at=_optional_moment(row[8]),
        runner_id=_optional_text(row[9], "A job's runner was not text."),
        heartbeat_at=_optional_moment(row[10]),
        cancel_requested_at=_optional_moment(row[11]),
        cancelled_by=_optional_text(row[12], "Who cancelled a job was not text."),
        run_id=None if run_id is None else UUID(run_id),
        attempts=require_integer(row[14], "A job's attempts were not an integer."),
        result=_optional_text(row[15], "A job's result was not text."),
        refusal=_optional_text(row[16], "A job's refusal was not text."),
        refusal_status=(
            None
            if refusal_status is None
            else require_integer(refusal_status, "A refusal's status was not an integer.")
        ),
    )


__all__ = [
    "FINISHED_STATUSES",
    "JOBS_ROUTE",
    "SERVICE_JOB_TABLES",
    "STAMP_FORMAT",
    "JobAccepted",
    "ServiceJob",
    "ServiceJobEvent",
    "ServiceJobRepository",
    "ServiceJobRunner",
    "ServiceJobStatus",
    "ServiceJobSummary",
    "SqlServiceJobRepository",
    "events_path",
    "job_path",
]

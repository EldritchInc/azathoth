"""Tests that a remote's jobs, events and runners are kept in either database (ADR 0138)."""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.persistence import Database, IntegrityError
from azathoth.persistence.repositories import open_repositories
from azathoth.remote.jobs import (
    FINISHED_STATUSES,
    SERVICE_JOB_TABLES,
    STAMP_FORMAT,
    ServiceJob,
    ServiceJobEvent,
    ServiceJobRepository,
    ServiceJobStatus,
    ServiceJobSummary,
    SqlServiceJobRepository,
)

START = datetime(2026, 11, 22, 22, 0, tzinfo=UTC)

FIRST = UUID("c1380000-0000-4000-8000-000000000001")

SECOND = UUID("c1380000-0000-4000-8000-000000000002")

THIRD = UUID("c1380000-0000-4000-8000-000000000003")

RUN_ID = UUID("c1380000-0000-4000-8000-0000000000a1")

ARGUMENTS = '{"workflow_id": "c1380000-0000-4000-8000-0000000000f1"}'


class Clock:
    """A clock a second later each time it is read, that a test may also move on."""

    def __init__(self) -> None:
        self._seconds: Iterator[int] = count()
        self.offset = timedelta()

    def __call__(self) -> datetime:
        return START + self.offset + timedelta(seconds=next(self._seconds))


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def jobs(
    database: Database,
    clock: Clock,
) -> ServiceJobRepository:
    """Open the job repository over an initialized database."""

    database.initialize(SERVICE_JOB_TABLES)

    return SqlServiceJobRepository(database, clock=clock)


def submitted(
    jobs: ServiceJobRepository,
    job_id: UUID = FIRST,
    *,
    principal: str = "Eris",
    call: str = "runs.run",
) -> ServiceJob:
    return jobs.submit(
        job_id,
        call=call,
        principal=principal,
        arguments=ARGUMENTS,
        resource="workflow c1380000-0000-4000-8000-0000000000f1",
    )


# Submitting and reading


def test_a_job_is_submitted_waiting_for_a_runner(
    jobs: ServiceJobRepository,
) -> None:
    job = submitted(jobs)

    assert job == ServiceJob(
        job_id=FIRST,
        call="runs.run",
        principal="Eris",
        arguments=ARGUMENTS,
        resource="workflow c1380000-0000-4000-8000-0000000000f1",
        status=ServiceJobStatus.QUEUED,
        submitted_at=START,
    )
    assert jobs.get(FIRST) == job
    assert jobs.get(SECOND) is None


def test_a_job_is_submitted_once(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs)

    with pytest.raises(IntegrityError):
        submitted(jobs)


def test_jobs_are_listed_newest_first_and_by_caller(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs, FIRST, principal="Eris")
    submitted(jobs, SECOND, principal="Discordia")
    submitted(jobs, THIRD, principal="Eris")

    assert [job.job_id for job in jobs.jobs()] == [THIRD, SECOND, FIRST]
    assert [job.job_id for job in jobs.jobs(principal="Eris")] == [THIRD, FIRST]
    assert [job.job_id for job in jobs.jobs(limit=1)] == [THIRD]

    with pytest.raises(ValueError, match="at least 1"):
        jobs.jobs(limit=0)


# Claiming


def test_a_runner_claims_the_job_waiting_longest(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs, FIRST)
    submitted(jobs, SECOND)

    claimed = jobs.claim("runner-a")

    assert claimed is not None
    assert claimed.job_id == FIRST
    assert claimed.status is ServiceJobStatus.RUNNING
    assert (claimed.runner_id, claimed.attempts) == ("runner-a", 1)
    assert claimed.started_at == claimed.heartbeat_at
    assert jobs.claim("runner-b") == jobs.get(SECOND)
    assert jobs.claim("runner-c") is None


def test_runners_claiming_together_never_take_one_job_twice(
    jobs: ServiceJobRepository,
    database: Database,
    clock: Clock,
) -> None:
    for number in range(12):
        submitted(jobs, UUID(int=number + 1))

    claimed: list[UUID] = []
    lock = threading.Lock()

    def run(
        runner_id: str,
    ) -> None:
        own = SqlServiceJobRepository(database, clock=clock)

        while (job := own.claim(runner_id)) is not None:
            with lock:
                claimed.append(job.job_id)

    threads = [threading.Thread(target=run, args=(f"runner-{n}",)) for n in range(4)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert sorted(claimed) == [UUID(int=number + 1) for number in range(12)]


# Events


def test_events_are_numbered_from_1_in_the_order_they_are_told(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs)
    first = jobs.append_event(FIRST, '{"type": "run_started"}')
    second = jobs.append_event(FIRST, '{"type": "run_finished"}')

    assert (first.sequence, second.sequence) == (1, 2)
    assert jobs.events(FIRST) == (first, second)
    assert jobs.events(FIRST, after=1) == (second,)
    assert jobs.events(FIRST, after=2) == ()
    assert jobs.events(SECOND) == ()


def test_each_job_numbers_its_own_events(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs, FIRST)
    submitted(jobs, SECOND)
    jobs.append_event(FIRST, "{}")

    assert jobs.append_event(SECOND, "{}") == ServiceJobEvent(
        job_id=SECOND,
        sequence=1,
        event="{}",
        recorded_at=jobs.events(SECOND)[0].recorded_at,
    )


def test_an_event_of_no_job_is_refused(
    jobs: ServiceJobRepository,
    database: Database,
) -> None:
    if database.dialect.value == "sqlite":
        pytest.skip("SQLite checks a foreign key only when told to.")

    with pytest.raises(IntegrityError):
        jobs.append_event(SECOND, "{}")


# Finishing


def test_a_job_its_runner_holds_ends_with_its_result(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs)
    jobs.claim("runner-a")
    jobs.record_run(FIRST, RUN_ID)

    assert jobs.finish(FIRST, "runner-a", ServiceJobStatus.SUCCEEDED, result='{"ok": true}')

    finished = jobs.get(FIRST)

    assert finished is not None
    assert finished.status is ServiceJobStatus.SUCCEEDED
    assert (finished.result, finished.run_id) == ('{"ok": true}', RUN_ID)
    assert finished.finished_at is not None


def test_a_failed_job_keeps_its_refusal(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs)
    jobs.claim("runner-a")
    refusal = '{"error": "Workflow X is not configured.", "code": "not_found"}'

    assert jobs.finish(
        FIRST,
        "runner-a",
        ServiceJobStatus.FAILED,
        refusal=refusal,
        refusal_status=404,
    )

    failed = jobs.get(FIRST)

    assert failed is not None
    assert (failed.status, failed.refusal, failed.refusal_status) == (
        ServiceJobStatus.FAILED,
        refusal,
        404,
    )


def test_a_job_is_finished_only_by_the_runner_holding_it(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs)

    assert not jobs.finish(FIRST, "runner-a", ServiceJobStatus.SUCCEEDED)

    jobs.claim("runner-a")

    assert not jobs.finish(FIRST, "runner-b", ServiceJobStatus.SUCCEEDED)
    assert jobs.finish(FIRST, "runner-a", ServiceJobStatus.SUCCEEDED)
    assert not jobs.finish(FIRST, "runner-a", ServiceJobStatus.FAILED)


def test_a_job_never_ends_queued_or_running(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs)
    jobs.claim("runner-a")

    for status in (ServiceJobStatus.QUEUED, ServiceJobStatus.RUNNING):
        with pytest.raises(ValueError, match="does not end"):
            jobs.finish(FIRST, "runner-a", status)

    assert {
        ServiceJobStatus.SUCCEEDED,
        ServiceJobStatus.FAILED,
        ServiceJobStatus.CANCELLED,
        ServiceJobStatus.INTERRUPTED,
    } == FINISHED_STATUSES


# Cancelling


def test_a_waiting_job_cancelled_is_cancelled_at_once_and_never_claimed(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs)
    cancelled = jobs.request_cancel(FIRST, "Eris")

    assert cancelled is not None
    assert cancelled.status is ServiceJobStatus.CANCELLED
    assert cancelled.cancelled_by == "Eris"
    assert cancelled.finished_at is not None
    assert jobs.claim("runner-a") is None


def test_a_running_job_cancelled_is_asked_once_and_its_runner_ends_it(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs)
    jobs.claim("runner-a")
    asked = jobs.request_cancel(FIRST, "Discordia")
    again = jobs.request_cancel(FIRST, "Eris")

    assert asked is not None and again is not None
    assert asked.status is ServiceJobStatus.RUNNING
    assert asked.cancel_requested_at is not None
    assert (again.cancel_requested_at, again.cancelled_by) == (
        asked.cancel_requested_at,
        "Discordia",
    )
    assert jobs.finish(FIRST, "runner-a", ServiceJobStatus.CANCELLED)


def test_a_finished_job_cancelled_is_left_as_it_ended(
    jobs: ServiceJobRepository,
) -> None:
    submitted(jobs)
    jobs.claim("runner-a")
    jobs.finish(FIRST, "runner-a", ServiceJobStatus.SUCCEEDED, result="{}")
    left = jobs.request_cancel(FIRST, "Eris")

    assert left is not None
    assert (left.status, left.cancel_requested_at) == (ServiceJobStatus.SUCCEEDED, None)
    assert jobs.request_cancel(SECOND, "Eris") is None


# Runners, and recovering what they left


def test_a_runner_beats_for_itself_and_every_job_it_holds(
    jobs: ServiceJobRepository,
    clock: Clock,
) -> None:
    runner = jobs.register_runner("runner-a", "host-1 pid 4711")
    submitted(jobs)
    claimed = jobs.claim("runner-a")
    clock.offset = timedelta(minutes=5)
    jobs.beat("runner-a")

    (beating,) = jobs.runners()
    held = jobs.get(FIRST)

    assert claimed is not None and claimed.heartbeat_at is not None
    assert held is not None and held.heartbeat_at is not None
    assert beating.server == "host-1 pid 4711"
    assert beating.started_at == runner.started_at
    assert beating.heartbeat_at > runner.heartbeat_at
    assert held.heartbeat_at > claimed.heartbeat_at


def test_a_retired_runner_is_forgotten(
    jobs: ServiceJobRepository,
) -> None:
    jobs.register_runner("runner-a", "host-1")
    jobs.retire_runner("runner-a")
    jobs.retire_runner("runner-a")

    assert jobs.runners() == ()


def test_a_job_whose_runner_stopped_beating_is_stalled(
    jobs: ServiceJobRepository,
    clock: Clock,
) -> None:
    submitted(jobs, FIRST)
    submitted(jobs, SECOND)
    jobs.claim("runner-a")
    jobs.claim("runner-b")
    clock.offset = timedelta(minutes=5)
    jobs.beat("runner-b")

    (stalled,) = jobs.stalled(START + timedelta(minutes=2))

    assert stalled.job_id == FIRST
    assert jobs.stalled(START) == ()


def test_a_stalled_job_is_queued_again_as_the_call_that_resumes_it(
    jobs: ServiceJobRepository,
    clock: Clock,
) -> None:
    submitted(jobs, FIRST)
    submitted(jobs, SECOND)
    jobs.claim("runner-a")
    jobs.append_event(FIRST, "{}")
    clock.offset = timedelta(minutes=5)
    (stalled,) = jobs.stalled(START + timedelta(minutes=2))
    resumed = f'{{"run_id": "{RUN_ID}"}}'

    assert jobs.requeue(stalled, call="runs.resume", arguments=resumed)
    assert not jobs.requeue(stalled, call="runs.resume", arguments=resumed)

    again = jobs.claim("runner-c")

    assert again is not None
    assert (again.job_id, again.call, again.arguments, again.attempts) == (
        FIRST,
        "runs.resume",
        resumed,
        2,
    )
    assert len(jobs.events(FIRST)) == 1


def test_a_stalled_job_nothing_resumes_is_interrupted(
    jobs: ServiceJobRepository,
    clock: Clock,
) -> None:
    submitted(jobs, call="benchmarks.run")
    jobs.claim("runner-a")
    clock.offset = timedelta(minutes=5)
    (stalled,) = jobs.stalled(START + timedelta(minutes=2))
    refusal = '{"error": "The server running it stopped.", "code": "interrupted"}'

    assert jobs.interrupt(stalled, refusal=refusal, refusal_status=503)
    assert not jobs.interrupt(stalled, refusal=refusal, refusal_status=503)

    interrupted = jobs.get(FIRST)

    assert interrupted is not None
    assert interrupted.status is ServiceJobStatus.INTERRUPTED
    assert interrupted.refusal == refusal
    assert not jobs.finish(FIRST, "runner-a", ServiceJobStatus.SUCCEEDED)


def test_a_stalled_job_that_beat_again_is_not_recovered(
    jobs: ServiceJobRepository,
    clock: Clock,
) -> None:
    submitted(jobs)
    jobs.claim("runner-a")
    clock.offset = timedelta(minutes=5)
    (stalled,) = jobs.stalled(START + timedelta(minutes=2))
    jobs.beat("runner-a")

    assert not jobs.requeue(stalled, call="runs.resume", arguments="{}")
    assert not jobs.interrupt(stalled, refusal="{}", refusal_status=503)
    assert jobs.finish(FIRST, "runner-a", ServiceJobStatus.SUCCEEDED)


# How the jobs stand


def test_the_summary_counts_what_waits_what_runs_and_the_runners_alive(
    jobs: ServiceJobRepository,
    clock: Clock,
) -> None:
    assert jobs.summary(START) == ServiceJobSummary(queued=0, running=0, runners=0)

    jobs.register_runner("runner-old", "host-1")
    clock.offset = timedelta(minutes=5)
    jobs.register_runner("runner-new", "host-2")
    submitted(jobs, FIRST)
    second = submitted(jobs, SECOND)
    submitted(jobs, THIRD)
    jobs.claim("runner-new")

    assert jobs.summary(START + timedelta(minutes=2)) == ServiceJobSummary(
        queued=2,
        running=1,
        runners=1,
        oldest_queued_at=second.submitted_at,
    )


# How moments are kept


def test_moments_are_kept_in_utc_with_microseconds_so_they_compare_as_text(
    database: Database,
) -> None:
    database.initialize(SERVICE_JOB_TABLES)
    eastern = timezone(timedelta(hours=-5))
    jobs = SqlServiceJobRepository(
        database,
        clock=lambda: datetime(2026, 11, 22, 17, 0, tzinfo=eastern),
    )
    submitted(jobs)

    with database.transaction(read_only=True) as session:
        row = session.fetchone("SELECT submitted_at FROM service_jobs")

    assert row == (datetime(2026, 11, 22, 22, 0, tzinfo=UTC).strftime(STAMP_FORMAT),)
    assert row == ("2026-11-22T22:00:00.000000+00:00",)


def test_an_instances_repositories_hold_its_jobs(
    tmp_path: Path,
) -> None:
    submitted(open_repositories(tmp_path / "azathoth.db").service_jobs)

    assert open_repositories(tmp_path / "azathoth.db").service_jobs.get(FIRST) is not None

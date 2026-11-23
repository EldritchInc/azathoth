"""Tests that a remote says how its jobs stand, at `GET /v1/service` (ADR 0138)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from azathoth.persistence.repositories import open_repositories
from azathoth.remote.jobs import (
    RUNNER_ALIVE_SECONDS,
    ServiceJobSummary,
    SqlServiceJobRepository,
)
from azathoth.remote.runners import DEFAULT_RUNNERS, STALL_SECONDS
from azathoth.remote.service import ServiceDescription
from tests.remote.asgi import call
from tests.remote.test_call_routes import ERIS, Served
from tests.remote.test_job_routes import submitted

LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)


def described(
    served: Served,
) -> ServiceDescription:
    return ServiceDescription.model_validate(call(served.app, "GET", "/v1/service").json())


def test_a_remote_that_runs_no_jobs_says_nothing_of_them(
    tmp_path: Path,
) -> None:
    assert described(Served(tmp_path / "azathoth.db", principal=ERIS, runs_jobs=False)).jobs is None


def test_a_remote_says_how_many_jobs_wait_and_run_and_since_when(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS)
    first = submitted(served)
    submitted(served)
    submitted(served)
    served.jobs.claim("runner-a")
    summary = described(served).jobs

    assert summary is not None
    assert (summary.queued, summary.running) == (2, 1)
    held = served.jobs.get(first)

    assert held is not None and summary.oldest_queued_at is not None
    assert summary.oldest_queued_at > held.submitted_at


def test_a_remote_counts_only_the_runners_that_beat_lately(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    served = Served(path, principal=ERIS)
    served.jobs.register_runner("runner-alive", "host-1")
    gone = SqlServiceJobRepository(open_repositories(path).database, clock=lambda: LONG_AGO)
    gone.register_runner("runner-gone", "host-2")

    assert described(served).jobs == ServiceJobSummary(queued=0, running=0, runners=1)


def test_a_runner_is_alive_for_as_long_as_its_jobs_are_left_to_it() -> None:
    assert STALL_SECONDS == RUNNER_ALIVE_SECONDS == 60.0
    assert DEFAULT_RUNNERS == 2
    assert timedelta(seconds=RUNNER_ALIVE_SECONDS) == timedelta(minutes=1)

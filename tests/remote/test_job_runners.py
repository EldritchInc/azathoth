"""Tests of a remote's job runners, and of recovering what they leave (ADR 0138, 0139)."""

import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from azathoth import api
from azathoth.persistence.repositories import Repositories, open_repositories
from azathoth.remote.calling import CallerInstances, job_signature
from azathoth.remote.jobs import ServiceJob, ServiceJobStatus, SqlServiceJobRepository
from azathoth.remote.runners import (
    FAILED_CODE,
    REQUEUED,
    RESUMED_AS_SUBMITTED,
    JobRunners,
    failed_message,
    interrupted_message,
)
from tests.api.test_run_started import ONCE_WORKFLOW_ID, appeared, stock_once
from tests.api.test_runs import (
    COUNT_WORKFLOW_ID,
    MISSING_ID,
    SLEEP_WORKFLOW_ID,
    stock,
)

LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)


class Remote:
    """A remote's database, holding the workflows a run needs, and the runners of its jobs."""

    def __init__(
        self,
        path: Path,
    ) -> None:
        with api.open(path) as instance:
            stock(instance)
            stock_once(instance)

        self.path = path
        self.repositories: Repositories = open_repositories(path)
        self.jobs = self.repositories.service_jobs
        self.instances = CallerInstances(self.repositories)

    def runners(
        self,
        *,
        count: int = 1,
        instances: Any = None,
        stall_seconds: float = 60.0,
    ) -> JobRunners:
        return JobRunners(
            self.jobs,
            self.instances if instances is None else instances,
            count=count,
            server="test server",
            poll_seconds=0.02,
            beat_seconds=0.05,
            stall_seconds=stall_seconds,
        )

    def submit(
        self,
        call: str,
        *,
        principal: str = "Eris",
        **arguments: object,
    ) -> UUID:
        job_id = uuid.uuid4()
        self.jobs.submit(
            job_id,
            call=call,
            principal=principal,
            arguments=job_signature(call).write_arguments(**arguments).decode(),
        )

        return job_id

    def job(
        self,
        job_id: UUID,
    ) -> ServiceJob:
        job = self.jobs.get(job_id)
        assert job is not None

        return job

    def event_types(
        self,
        job_id: UUID,
    ) -> list[str]:
        return [json.loads(event.event)["type"] for event in self.jobs.events(job_id)]


@pytest.fixture
def remote(
    tmp_path: Path,
) -> Remote:
    sqlite = tmp_path / "azathoth.db"
    sqlite.touch()

    return Remote(sqlite)


def until(
    holds: Callable[[], bool],
    *,
    seconds: float = 20.0,
) -> None:
    """Wait for something to hold, failing once it has not for `seconds`."""

    deadline = time.monotonic() + seconds

    while not holds():
        assert time.monotonic() < deadline, "It never held."
        time.sleep(0.02)


def finished(
    remote: Remote,
    job_id: UUID,
) -> ServiceJob:
    until(lambda: remote.job(job_id).status.finished)

    return remote.job(job_id)


# Running a job


def test_a_job_runs_as_its_call_and_keeps_its_result_and_every_event(
    remote: Remote,
) -> None:
    job_id = remote.submit(
        "runs.run",
        workflow_id=COUNT_WORKFLOW_ID,
        input=api.RunInput(payload="one two three"),
    )

    with remote.runners():
        job = finished(remote, job_id)

    assert job.status is ServiceJobStatus.SUCCEEDED
    assert job.result is not None
    result = job_signature("runs.run").read_result(job.result.encode())

    assert isinstance(result, api.RunResult)
    assert (result.succeeded, result.result) == (True, 3)
    assert remote.event_types(job_id) == [
        "run_started",
        "step_started",
        "step_finished",
        "context_changed",
        "run_finished",
    ]
    assert [event.sequence for event in remote.jobs.events(job_id)] == [1, 2, 3, 4, 5]
    assert remote.repositories.runs.get(result.run_id) is not None


def test_a_job_the_service_api_refuses_ends_failed_with_the_refusal_a_call_would_give(
    remote: Remote,
) -> None:
    job_id = remote.submit("runs.run", workflow_id=MISSING_ID)

    with remote.runners():
        job = finished(remote, job_id)

    assert job.status is ServiceJobStatus.FAILED
    assert job.refusal_status == 404
    assert job.refusal is not None
    assert json.loads(job.refusal) == {
        "error": f"Workflow {MISSING_ID} is not configured.",
        "code": "not_found",
        "kinds": ["not_found", "error"],
    }


def test_a_job_whose_arguments_are_not_its_calls_ends_failed(
    remote: Remote,
) -> None:
    job_id = uuid.uuid4()
    remote.jobs.submit(job_id, call="runs.run", principal="Eris", arguments='{"flavour": 1}')

    with remote.runners():
        job = finished(remote, job_id)

    assert (job.status, job.refusal_status) == (ServiceJobStatus.FAILED, 400)
    assert job.refusal is not None
    assert json.loads(job.refusal)["code"] == "invalid_argument"


def test_a_job_that_fails_in_a_way_the_service_api_does_not_name_says_so(
    remote: Remote,
) -> None:
    class Broken:
        def instance(
            self,
            author: str,
        ) -> api.Azathoth:
            raise RuntimeError("The instance could not be made.")

    job_id = remote.submit("runs.run", workflow_id=COUNT_WORKFLOW_ID)

    with remote.runners(instances=Broken()):
        job = finished(remote, job_id)

    assert (job.status, job.refusal_status) == (ServiceJobStatus.FAILED, 500)
    assert job.refusal is not None
    assert json.loads(job.refusal) == {"error": failed_message("runs.run"), "code": FAILED_CODE}
    assert failed_message("runs.run") == "runs.run failed at the remote; its log says why."


def test_runners_run_jobs_at_once_and_in_the_order_they_were_submitted(
    remote: Remote,
) -> None:
    first = remote.submit(
        "runs.run",
        workflow_id=SLEEP_WORKFLOW_ID,
        input=api.RunInput(payload="x"),
    )
    second = remote.submit(
        "runs.run",
        workflow_id=SLEEP_WORKFLOW_ID,
        input=api.RunInput(payload="x"),
    )
    third = remote.submit("runs.run", workflow_id=COUNT_WORKFLOW_ID)

    with remote.runners(count=2) as runners:
        until(lambda: runners.running == {first, second})

        assert remote.job(third).status is ServiceJobStatus.QUEUED

        remote.jobs.request_cancel(first, "Eris")
        remote.jobs.request_cancel(second, "Eris")
        finished(remote, third)


# Cancelling


def test_a_running_job_asked_to_stop_stops_and_ends_cancelled(
    remote: Remote,
) -> None:
    job_id = remote.submit(
        "runs.run",
        workflow_id=SLEEP_WORKFLOW_ID,
        input=api.RunInput(payload="x"),
    )

    with remote.runners():
        until(lambda: "step_started" in remote.event_types(job_id))
        remote.jobs.request_cancel(job_id, "Discordia")
        job = finished(remote, job_id)

    assert (job.status, job.cancelled_by, job.refusal_status) == (
        ServiceJobStatus.CANCELLED,
        "Discordia",
        409,
    )
    assert job.refusal is not None
    assert json.loads(job.refusal)["code"] == "run_cancelled"
    assert "run_finished" not in remote.event_types(job_id)


def test_a_job_cancelled_before_it_ran_never_runs(
    remote: Remote,
) -> None:
    job_id = remote.submit("runs.run", workflow_id=COUNT_WORKFLOW_ID)
    remote.jobs.request_cancel(job_id, "Eris")
    after = remote.submit("runs.run", workflow_id=COUNT_WORKFLOW_ID)

    with remote.runners():
        finished(remote, after)

    assert remote.job(job_id).status is ServiceJobStatus.CANCELLED
    assert remote.jobs.events(job_id) == ()


# Runners, and stopping


def test_runners_are_recorded_while_they_run_and_beat_for_the_jobs_they_hold(
    remote: Remote,
) -> None:
    job_id = remote.submit(
        "runs.run",
        workflow_id=SLEEP_WORKFLOW_ID,
        input=api.RunInput(payload="x"),
    )

    with remote.runners(count=2) as runners:
        until(lambda: remote.job(job_id).status is ServiceJobStatus.RUNNING)
        started = remote.job(job_id).heartbeat_at
        recorded = remote.jobs.runners()

        assert started is not None
        until(lambda: (remote.job(job_id).heartbeat_at or started) > started)
        assert sorted(runner.runner_id for runner in recorded) == sorted(runners.runner_ids)
        assert {runner.server for runner in recorded} == {"test server"}

        remote.jobs.request_cancel(job_id, "Eris")

    assert remote.jobs.runners() == ()


def test_a_server_that_stops_hands_a_run_back_to_be_resumed_by_the_run_it_named(
    remote: Remote,
) -> None:
    marker = remote.path.parent / "slept"
    job_id = remote.submit(
        "runs.run",
        workflow_id=ONCE_WORKFLOW_ID,
        input=api.RunInput(payload=str(marker)),
    )

    with remote.runners():
        appeared(marker)

    handed_back = remote.job(job_id)
    (named,) = [
        json.loads(event.event)["run_id"]
        for event in remote.jobs.events(job_id)
        if json.loads(event.event)["type"] == "run_started"
    ]

    assert (handed_back.status, handed_back.call) == (ServiceJobStatus.QUEUED, "runs.run")
    assert handed_back.run_id == UUID(named)

    with remote.runners():
        job = finished(remote, job_id)

    assert (job.status, job.attempts) == (ServiceJobStatus.SUCCEEDED, 2)
    assert job.result is not None
    assert json.loads(job.result)["run_id"] == named
    assert json.loads(job.result)["result"] == 1
    assert remote.event_types(job_id).count("run_started") == 2


def test_a_server_that_stops_ends_a_job_its_caller_asked_to_stop_as_cancelled(
    remote: Remote,
) -> None:
    job_id = remote.submit(
        "runs.run",
        workflow_id=SLEEP_WORKFLOW_ID,
        input=api.RunInput(payload="x"),
    )
    runners = remote.runners()
    runners.start()
    until(lambda: "step_started" in remote.event_types(job_id))
    remote.jobs.request_cancel(job_id, "Eris")
    runners.stop()

    assert finished(remote, job_id).status is ServiceJobStatus.CANCELLED


def test_a_count_of_runners_below_1_is_refused_and_runners_start_once(
    remote: Remote,
) -> None:
    with pytest.raises(ValueError, match="at least one job at once"):
        remote.runners(count=0)

    with remote.runners() as runners, pytest.raises(RuntimeError, match="already started"):
        runners.start()


# Recovering what a runner that stopped beating left


def stalled(
    remote: Remote,
    call: str,
    **arguments: Any,
) -> UUID:
    """Submit a job and leave it running under a runner that stopped beating long ago."""

    job_id = remote.submit(call, **arguments)
    gone = SqlServiceJobRepository(remote.repositories.database, clock=lambda: LONG_AGO)
    claimed = gone.claim("runner-gone")

    assert claimed is not None and claimed.job_id == job_id

    return job_id


def test_a_resume_left_by_a_runner_that_stopped_is_queued_again_as_it_was(
    remote: Remote,
) -> None:
    run_id = UUID("c1390000-0000-4000-8000-0000000000aa")
    job_id = stalled(remote, "runs.resume", run_id=run_id)

    assert remote.runners().recover() == 1

    job = remote.job(job_id)

    assert (job.status, job.call, job.runner_id) == (ServiceJobStatus.QUEUED, "runs.resume", None)
    assert json.loads(job.arguments) == {"run_id": str(run_id)}


def test_a_job_nothing_resumes_left_by_a_runner_that_stopped_is_interrupted(
    remote: Remote,
) -> None:
    job_id = stalled(remote, "benchmarks.run", benchmark_id=MISSING_ID, workflow_id=MISSING_ID)

    assert remote.runners().recover() == 1

    job = remote.job(job_id)

    assert (job.status, job.refusal_status) == (ServiceJobStatus.INTERRUPTED, 409)
    assert job.refusal is not None
    assert json.loads(job.refusal) == {
        "error": interrupted_message("benchmarks.run"),
        "code": "interrupted",
    }


def test_a_run_left_before_it_named_its_run_is_run_again_as_submitted(
    remote: Remote,
) -> None:
    job_id = stalled(
        remote,
        "runs.run",
        workflow_id=COUNT_WORKFLOW_ID,
        input=api.RunInput(payload="one two"),
    )

    assert remote.runners().recover() == 1
    assert (remote.job(job_id).status, remote.job(job_id).call) == (
        ServiceJobStatus.QUEUED,
        "runs.run",
    )

    with remote.runners():
        job = finished(remote, job_id)

    assert (job.status, job.attempts) == (ServiceJobStatus.SUCCEEDED, 2)
    assert job.result is not None
    assert json.loads(job.result)["result"] == 2


def test_a_run_whose_named_run_never_journaled_runs_anew(
    remote: Remote,
) -> None:
    job_id = stalled(
        remote,
        "runs.run",
        workflow_id=COUNT_WORKFLOW_ID,
        input=api.RunInput(payload="one two three"),
    )
    never = UUID("c1390000-0000-4000-8000-0000000000bb")
    remote.jobs.record_run(job_id, never)

    with remote.runners(stall_seconds=0.1):
        job = finished(remote, job_id)

    assert job.status is ServiceJobStatus.SUCCEEDED
    assert job.result is not None
    assert json.loads(job.result)["result"] == 3
    assert job.run_id is not None and job.run_id != never
    assert json.loads(job.result)["run_id"] == str(job.run_id)


def test_only_runs_resumes_and_invocations_go_on_where_they_were() -> None:
    assert frozenset({"runs.resume", "invocations.resume", "runs.invoke"}) == RESUMED_AS_SUBMITTED
    assert RESUMED_AS_SUBMITTED | {"runs.run"} == REQUEUED
    assert interrupted_message("runs.run") == (
        "The server running this job stopped before it finished, and nothing resumes "
        "runs.run; submit it again."
    )
    assert interrupted_message("benchmarks.run") == (
        "The server running this job stopped before it finished, and nothing resumes "
        "benchmarks.run; submit it again."
    )


def test_running_runners_recover_a_stalled_job_and_run_it(
    remote: Remote,
) -> None:
    job_id = stalled(remote, "runs.invoke", workflow_id=MISSING_ID, input="x")

    with remote.runners(stall_seconds=60.0):
        job = finished(remote, job_id)

    assert job.status is ServiceJobStatus.SUCCEEDED
    assert job.attempts == 2
    assert job.runner_id != "runner-gone"


def test_a_job_whose_runner_still_beats_is_never_recovered(
    remote: Remote,
) -> None:
    job_id = remote.submit(
        "runs.run",
        workflow_id=SLEEP_WORKFLOW_ID,
        input=api.RunInput(payload="x"),
    )

    with remote.runners(stall_seconds=60.0) as runners:
        until(lambda: remote.job(job_id).status is ServiceJobStatus.RUNNING)

        assert runners.recover() == 0

        remote.jobs.request_cancel(job_id, "Eris")

"""Tests that a remote's jobs answer as local calls do, and outlive its servers (ADR 0138).

Each test runs the same job locally and through a remote over one SQLite
database, with the remote's own runners, and requires the same answer.
"""

import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from azathoth import api
from azathoth.api.connected import ConnectedInstance
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import Action, Principal
from azathoth.remote.calling import CallerInstances, job_signature
from azathoth.remote.jobs import ServiceJobStatus, SqlServiceJobRepository
from azathoth.remote.runners import JobRunners, interrupted_message
from tests.api.test_invoke import promote
from tests.api.test_runs import COUNT_WORKFLOW_ID, SLEEP_WORKFLOW_ID, stock
from tests.remote.asgi import AsgiHttp
from tests.remote.test_call_routes import ERIS, Served
from tests.remote.test_conditions import Refusing

URL = "http://remote.test"

LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)

DISCORDIA = Principal(name="Discordia", owner=True)


@pytest.fixture
def path(
    tmp_path: Path,
) -> Path:
    """Return a database holding the run tests' workflows, the word count one promoted."""

    database = tmp_path / "azathoth.db"
    database.touch()

    with api.open(database) as instance:
        stock(instance)

    promote(str(database), COUNT_WORKFLOW_ID)

    return database


@pytest.fixture
def served(
    path: Path,
) -> Served:
    return Served(path, principal=ERIS)


def runners(
    path: Path,
    served: Served,
    *,
    stall_seconds: float = 60.0,
) -> JobRunners:
    return JobRunners(
        served.jobs,
        CallerInstances(open_repositories(path)),
        count=2,
        poll_seconds=0.02,
        beat_seconds=0.05,
        stall_seconds=stall_seconds,
    )


@pytest.fixture
def running(
    path: Path,
    served: Served,
) -> Iterator[JobRunners]:
    with runners(path, served) as started:
        yield started


def connected(
    served: Served,
) -> ConnectedInstance:
    return api.connect(URL, token="azr_test", http=AsgiHttp(served.app))


def both(
    path: Path,
    served: Served,
    job: Callable[[api.Instance, list[str]], Any],
) -> tuple[tuple[Any, list[str]], tuple[Any, list[str]]]:
    """Return what a job answers and tells, run locally and through the remote."""

    here: list[str] = []
    there: list[str] = []

    with api.open(path) as local:
        answered_here = job(local, here)

    with connected(served) as remote:
        answered_there = job(remote, there)

    return (answered_here, here), (answered_there, there)


def kinds(
    told: list[str],
) -> Callable[[Any], None]:
    return lambda event: told.append(event.type)


# The same answers


def test_an_invocation_through_a_remote_answers_as_a_local_one(
    path: Path,
    served: Served,
    running: JobRunners,
) -> None:
    (here, told_here), (there, told_there) = both(
        path,
        served,
        lambda instance, told: instance.runs.invoke(
            COUNT_WORKFLOW_ID,
            input="one two three",
            idempotency_key=f"order-{len(told)}-{uuid.uuid4()}",
            on_event=kinds(told),
        ),
    )

    assert isinstance(there, api.InvocationOutcome)
    assert (there.status, there.result) == (here.status, here.result)
    assert (there.status, there.result) == ("succeeded", {"result": 3})
    assert told_there == told_here


def test_a_benchmark_run_through_a_remote_answers_as_a_local_one(
    path: Path,
    served: Served,
    running: JobRunners,
) -> None:
    with api.open(path) as local:
        benchmark = local.benchmarks.create("words", "Counts words.").benchmark.id

        for text, count in (("one two", 2), ("one two three", 3)):
            local.benchmarks.add_case(
                benchmark,
                input=api.RunInput(payload=text),
                comparison="exact",
                expected={"result": count},
            )

    (here, told_here), (there, told_there) = both(
        path,
        served,
        lambda instance, told: instance.benchmarks.run(
            benchmark,
            COUNT_WORKFLOW_ID,
            on_event=kinds(told),
        ),
    )

    assert type(there) is type(here)
    assert told_there == told_here == ["case_started", "case_finished"] * 2
    assert there.execution_id != here.execution_id
    assert (there.case_count, there.kind) == (here.case_count, here.kind)
    assert there.case_count == 2
    assert [
        (candidate.workflow_id, candidate.cases_run, candidate.cases_passed, candidate.accuracy)
        for candidate in there.candidates
    ] == [
        (candidate.workflow_id, candidate.cases_run, candidate.cases_passed, candidate.accuracy)
        for candidate in here.candidates
    ]


# Servers that stop


def stalled(
    served: Served,
    path: Path,
    call: str,
    **arguments: Any,
) -> uuid.UUID:
    """Submit a job and leave it with a runner that stopped beating long ago."""

    job_id = uuid.uuid4()
    gone = SqlServiceJobRepository(open_repositories(path).database, clock=lambda: LONG_AGO)
    gone.submit(
        job_id,
        call=call,
        principal="Eris",
        arguments=job_signature(call).write_arguments(**arguments).decode(),
    )
    claimed = gone.claim("runner-gone")

    assert claimed is not None and claimed.job_id == job_id

    return job_id


def test_an_invocation_left_by_a_server_that_stopped_is_resumed_and_followed_to_its_end(
    path: Path,
    served: Served,
) -> None:
    job_id = stalled(
        served,
        path,
        "runs.invoke",
        workflow_id=COUNT_WORKFLOW_ID,
        input="one two",
        idempotency_key="order-412",
    )

    with runners(path, served, stall_seconds=0.1), connected(served) as remote:
        outcome = remote.jobs.follow(job_id)
        job = remote.jobs.get(job_id)

    assert (outcome.status, outcome.result, outcome.idempotency_key) == (
        "succeeded",
        {"result": 2},
        "order-412",
    )
    assert (job.status, job.attempts) == (ServiceJobStatus.SUCCEEDED, 2)


def test_a_run_left_by_a_server_that_stopped_is_refused_saying_how_to_resume_it(
    path: Path,
    served: Served,
) -> None:
    job_id = stalled(served, path, "runs.run", workflow_id=COUNT_WORKFLOW_ID)

    with (
        runners(path, served, stall_seconds=0.1),
        connected(served) as remote,
        pytest.raises(api.RemoteRefusedError) as caught,
    ):
        remote.jobs.follow(job_id)

    assert (caught.value.status, caught.value.refusal) == (409, "interrupted")
    assert str(caught.value) == interrupted_message("runs.run")


def test_a_job_queued_while_no_server_runs_jobs_runs_once_one_does(
    path: Path,
    served: Served,
) -> None:
    with connected(served) as remote:
        accepted = remote.jobs.submit(
            "runs.run",
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="one two"),
        )
        time.sleep(0.1)

        assert remote.jobs.get(accepted.job_id).status is ServiceJobStatus.QUEUED

        with runners(path, served):
            result = remote.jobs.follow(accepted.job_id)

    assert result.result == 2


# Who may follow a job


def test_a_restricted_run_is_followed_only_by_who_may_read_restricted(
    path: Path,
    running: JobRunners,
) -> None:
    refused = Served(path, principal=ERIS, policy=Refusing(Action.READ_RESTRICTED))

    with connected(refused) as remote, pytest.raises(api.PermissionDeniedError):
        remote.runs.run(
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="one two"),
            sensitivity=api.Sensitivity.RESTRICTED,
        )

    with connected(Served(path, principal=ERIS)) as allowed:
        result = allowed.runs.run(
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="one two"),
            sensitivity=api.Sensitivity.RESTRICTED,
        )

    assert result.result == 2


def test_another_callers_job_is_followed_by_who_may_read_runs(
    path: Path,
    served: Served,
    running: JobRunners,
) -> None:
    with connected(served) as eris:
        accepted = eris.jobs.submit("runs.run", COUNT_WORKFLOW_ID, input=api.RunInput(payload="a"))

    with connected(Served(path, principal=DISCORDIA)) as allowed:
        assert allowed.jobs.follow(accepted.job_id).result == 1
        assert allowed.jobs.list() == ()

    refused = Served(path, principal=DISCORDIA, policy=Refusing(Action.READ_RUNS))

    with connected(refused) as other, pytest.raises(api.PermissionDeniedError):
        other.jobs.get(accepted.job_id)


def test_a_job_of_another_caller_is_stopped_only_by_who_may_do_what_it_does(
    path: Path,
    served: Served,
) -> None:
    with connected(served) as eris:
        accepted = eris.jobs.submit("runs.run", SLEEP_WORKFLOW_ID, input=api.RunInput(payload="x"))

    refused = Served(path, principal=DISCORDIA, policy=Refusing(Action.RUN_WORKFLOW))

    with connected(refused) as other, pytest.raises(api.PermissionDeniedError):
        other.jobs.cancel(accepted.job_id)

    with connected(Served(path, principal=DISCORDIA)) as allowed:
        cancelled = allowed.jobs.cancel(accepted.job_id)

    assert (cancelled.status, cancelled.cancelled_by) == (ServiceJobStatus.CANCELLED, "Discordia")

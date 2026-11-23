"""Tests of calling a job through a connected instance, as a local one calls it (ADR 0138)."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from azathoth import api
from azathoth.api import connected as connected_module
from azathoth.api.connected import ConnectedInstance
from azathoth.persistence.repositories import open_repositories
from azathoth.remote.calling import CallerInstances
from azathoth.remote.jobs import ServiceJobStatus
from azathoth.remote.runners import JobRunners
from tests.api.test_runs import COUNT_WORKFLOW_ID, MISSING_ID, SLEEP_WORKFLOW_ID, stock
from tests.remote.asgi import AsgiHttp, AsgiStream
from tests.remote.test_call_routes import ERIS, Served
from tests.remote.test_service_routes import GUEST

URL = "http://remote.test"

TOKEN = "azr_test"


class Cutting(AsgiHttp):
    """An in-process client whose streams drop after a few events, as a flaky network's do."""

    def __init__(
        self,
        app: Any,
        *,
        events: int,
        times: int,
    ) -> None:
        super().__init__(app)
        self.events = events
        self.times = times
        self.streams = 0

    @contextmanager
    def stream(
        self,
        method: str,
        url: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Iterator[AsgiStream]:
        self.streams += 1

        with super().stream(method, url, content=content, headers=headers) as response:
            if self.streams > self.times:
                yield response
                return

            yield _Cut(response, self.events)


class _Cut(AsgiStream):
    """A stream that ends after a number of events, before its job does."""

    def __init__(
        self,
        whole: AsgiStream,
        events: int,
    ) -> None:
        self.status_code = whole.status_code
        self._whole = whole
        self._events = events

    def iter_lines(
        self,
    ) -> Iterator[str]:
        ended = 0

        for line in self._whole.iter_lines():
            if ended >= self._events:
                return

            yield line

            if not line:
                ended += 1


@pytest.fixture
def path(
    tmp_path: Path,
) -> Path:
    database = tmp_path / "azathoth.db"
    database.touch()

    with api.open(database) as instance:
        stock(instance)

    return database


@pytest.fixture
def served(
    path: Path,
) -> Served:
    return Served(path, principal=ERIS)


@pytest.fixture
def runners(
    path: Path,
    served: Served,
) -> Iterator[JobRunners]:
    running = JobRunners(
        served.jobs,
        CallerInstances(open_repositories(path)),
        count=2,
        poll_seconds=0.02,
        beat_seconds=0.05,
    )

    with running:
        yield running


def connected(
    served: Served,
    http: AsgiHttp | None = None,
) -> ConnectedInstance:
    return api.connect(URL, token=TOKEN, http=http if http is not None else AsgiHttp(served.app))


# Running a job as the local call runs


def test_a_run_through_a_remote_returns_and_tells_what_a_local_run_does(
    path: Path,
    served: Served,
    runners: JobRunners,
) -> None:
    told: list[api.RunEvent] = []
    heard: list[api.RunEvent] = []

    with api.open(path) as local:
        here = local.runs.run(
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="one two three"),
            on_event=told.append,
        )

    with connected(served) as remote:
        there = remote.runs.run(
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="one two three"),
            on_event=heard.append,
        )

    assert isinstance(there, api.RunResult)
    assert (there.succeeded, there.result) == (here.succeeded, here.result) == (True, 3)
    assert there.run_id != here.run_id
    assert [event.type for event in heard] == [event.type for event in told]
    assert all(type(event) is type(local) for event, local in zip(heard, told, strict=True))


def test_a_job_the_policy_refuses_is_refused_as_a_call_is(
    path: Path,
    runners: JobRunners,
) -> None:
    with (
        connected(Served(path, principal=GUEST)) as guest,
        pytest.raises(api.PermissionDeniedError),
    ):
        guest.runs.run(COUNT_WORKFLOW_ID)


def test_a_job_that_fails_raises_what_the_local_call_raises(
    path: Path,
    served: Served,
    runners: JobRunners,
) -> None:
    with api.open(path) as local, pytest.raises(api.NotFoundError) as here:
        local.runs.run(MISSING_ID)

    with connected(served) as remote, pytest.raises(api.NotFoundError) as there:
        remote.runs.run(MISSING_ID)

    assert type(there.value) is type(here.value)
    assert str(there.value) == str(here.value)


def test_a_remote_that_runs_no_jobs_refuses_them(
    path: Path,
) -> None:
    with (
        connected(Served(path, principal=ERIS, runs_jobs=False)) as remote,
        pytest.raises(api.RemoteRefusedError) as caught,
    ):
        remote.runs.run(COUNT_WORKFLOW_ID)

    assert (caught.value.status, caught.value.refusal) == (501, "job")


# Cancelling


def test_a_job_whose_token_is_cancelled_is_stopped_at_the_remote_and_raises(
    served: Served,
    runners: JobRunners,
) -> None:
    token = api.CancellationToken()
    heard: list[api.RunEvent] = []

    def cancel_when_started(
        event: api.RunEvent,
    ) -> None:
        heard.append(event)

        if event.type == "step_started":
            token.cancel()

    with connected(served) as remote, pytest.raises(api.RunCancelledError) as caught:
        remote.runs.run(
            SLEEP_WORKFLOW_ID,
            input=api.RunInput(payload="x"),
            on_event=cancel_when_started,
            cancel=token,
        )

    (job,) = served.jobs.jobs()

    assert str(caught.value) == "The run was cancelled."
    assert (job.status, job.cancelled_by) == (ServiceJobStatus.CANCELLED, "Eris")
    assert not any(event.type == "run_finished" for event in heard)


def test_a_token_cancelled_beforehand_sends_nothing(
    served: Served,
) -> None:
    token = api.CancellationToken()
    token.cancel()
    http = AsgiHttp(served.app)

    with connected(served, http) as remote, pytest.raises(api.RunCancelledError):
        remote.runs.run(COUNT_WORKFLOW_ID, cancel=token)

    assert http.sent == []


# Following


def test_a_callback_that_raises_is_told_no_more_and_the_job_goes_on(
    served: Served,
    runners: JobRunners,
) -> None:
    heard: list[str] = []

    def once(
        event: api.RunEvent,
    ) -> None:
        heard.append(event.type)
        raise RuntimeError("Told enough.")

    with connected(served) as remote:
        result = remote.runs.run(
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="a b"),
            on_event=once,
        )

    assert heard == ["run_started"]
    assert result.result == 2


def test_a_dropped_stream_is_followed_again_from_the_last_event_seen(
    served: Served,
    runners: JobRunners,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(connected_module, "RECONNECT_SECONDS", 0.0)
    http = Cutting(served.app, events=2, times=2)
    heard: list[str] = []

    with connected(served, http) as remote:
        result = remote.runs.run(
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="one two three"),
            on_event=lambda event: heard.append(event.type),
        )

    assert result.result == 3
    assert heard == [
        "run_started",
        "step_started",
        "step_finished",
        "context_changed",
        "run_finished",
    ]
    assert http.streams >= 3


def test_a_stream_dropped_too_often_is_given_up_while_the_job_goes_on(
    served: Served,
    runners: JobRunners,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(connected_module, "RECONNECT_SECONDS", 0.0)
    http = Cutting(served.app, events=0, times=100)

    with connected(served, http) as remote, pytest.raises(api.RemoteUnreachableError) as caught:
        remote.runs.run(SLEEP_WORKFLOW_ID, input=api.RunInput(payload="x"))

    (job,) = served.jobs.jobs()

    assert str(caught.value) == (
        f"The remote at {URL} dropped the events of job {job.job_id} 6 times, so they are no "
        "longer followed; the job goes on there, and jobs.get finds it."
    )
    assert http.streams == 6
    served.jobs.request_cancel(job.job_id, "Eris")


# Jobs apart from their calls


def test_a_job_submitted_apart_is_followed_later_to_its_result(
    served: Served,
    runners: JobRunners,
) -> None:
    with connected(served) as remote:
        accepted = remote.jobs.submit(
            "runs.run",
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="one two"),
        )
        heard: list[str] = []
        result = remote.jobs.follow(
            accepted.job_id,
            on_event=lambda event: heard.append(event.type),
        )
        view = remote.jobs.get(accepted.job_id)
        listed = remote.jobs.list()

    assert result.result == 2
    assert heard[0] == "run_started"
    assert (view.status, view.has_result) == (ServiceJobStatus.SUCCEEDED, True)
    assert [summary.job_id for summary in listed] == [accepted.job_id]


def test_a_job_submitted_apart_is_cancelled_apart(
    served: Served,
) -> None:
    with connected(served) as remote:
        accepted = remote.jobs.submit("runs.run", COUNT_WORKFLOW_ID)
        cancelled = remote.jobs.cancel(accepted.job_id)

        with pytest.raises(api.RunCancelledError):
            remote.jobs.follow(accepted.job_id)

    assert cancelled.status is ServiceJobStatus.CANCELLED


def test_a_job_submitted_apart_takes_no_callback_or_token(
    served: Served,
) -> None:
    with connected(served) as remote, pytest.raises(TypeError, match="takes no cancel"):
        remote.jobs.submit("runs.run", COUNT_WORKFLOW_ID, cancel=api.CancellationToken())


def test_a_closed_instance_follows_no_job(
    served: Served,
) -> None:
    remote = connected(served)
    remote.close()

    with pytest.raises(api.InstanceClosedError):
        remote.jobs.list()

    with pytest.raises(api.InstanceClosedError):
        remote.runs.run(COUNT_WORKFLOW_ID)

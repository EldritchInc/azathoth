"""Tests of streaming a job's events as they are told, to who may see them (ADR 0138)."""

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from azathoth.persistence.repositories import open_repositories
from azathoth.remote import Action, AuditEventKind, Principal
from azathoth.remote.jobs import (
    JobView,
    ServiceJobEvent,
    ServiceJobStatus,
    SqlServiceJobRepository,
)
from azathoth.remote.server import (
    EVENT_STREAM_MEDIA_TYPE,
    FINISHED_EVENT,
    JOB_EVENT,
    NO_JOBS_MESSAGE,
    server_sent,
)
from tests.remote.asgi import Answer, send
from tests.remote.test_call_routes import ERIS, Served
from tests.remote.test_conditions import Refusing
from tests.remote.test_job_routes import RESULT, RUN_ID, submitted

DISCORDIA = Principal(name="Discordia", owner=True)

MISSING = UUID("c13c0000-0000-4000-8000-0000000000ff")

TOLD = ['{"type": "run_started"}', '{"type": "step_started"}', '{"type": "run_finished"}']


class Frame:
    """One server-sent event, or a comment, as a stream sent it."""

    def __init__(
        self,
        text: str,
    ) -> None:
        fields: dict[str, str] = {}
        self.comment: str | None = None

        for line in text.split("\n"):
            if line.startswith(":"):
                self.comment = line[1:].strip()
            else:
                name, _, value = line.partition(": ")
                fields[name] = value

        self.id = fields.get("id")
        self.event = fields.get("event")
        self.data = fields.get("data")

    def json(self) -> Any:
        assert self.data is not None

        return json.loads(self.data)


def frames(
    answer: Answer,
) -> list[Frame]:
    return [Frame(text) for text in answer.body.decode().split("\n\n") if text]


def events(
    served: Served,
    job_id: UUID,
    *,
    last: str | None = None,
    query: str = "",
) -> Answer:
    """Follow a job's events to the end, as a client that last saw `last` does."""

    async def following() -> Answer:
        app: Any = served.app

        if last is None:
            return await send(app, "GET", f"/v1/jobs/{job_id}/events{query}")

        def with_last(
            scope: dict[str, Any],
            receive: Any,
            reply: Any,
        ) -> Any:
            scope["headers"] = [*scope["headers"], (b"last-event-id", last.encode())]

            return app(scope, receive, reply)

        return await send(with_last, "GET", f"/v1/jobs/{job_id}/events{query}")

    return asyncio.run(following())


def told(
    served: Served,
    job_id: UUID,
) -> None:
    """Tell a job's events and end it, as a runner would."""

    claimed = served.jobs.claim("runner-test")
    assert claimed is not None and claimed.job_id == job_id

    for event in TOLD:
        served.jobs.append_event(job_id, event)

    served.jobs.finish(job_id, "runner-test", ServiceJobStatus.SUCCEEDED, result=json.dumps(RESULT))


@pytest.fixture
def served(
    tmp_path: Path,
) -> Served:
    return Served(tmp_path / "azathoth.db", principal=ERIS)


# What a stream sends


def test_a_jobs_events_are_streamed_in_order_each_numbered_then_the_job_as_it_ended(
    served: Served,
) -> None:
    job_id = submitted(served)
    told(served, job_id)
    answer = events(served, job_id)
    (*sent, ended) = frames(answer)

    assert answer.status == 200
    assert answer.headers["content-type"].startswith(EVENT_STREAM_MEDIA_TYPE)
    assert answer.headers["cache-control"] == "no-cache"
    assert [(frame.id, frame.event, frame.json()) for frame in sent] == [
        ("1", JOB_EVENT, {"type": "run_started"}),
        ("2", JOB_EVENT, {"type": "step_started"}),
        ("3", JOB_EVENT, {"type": "run_finished"}),
    ]
    assert (ended.id, ended.event) == ("3", FINISHED_EVENT)

    view = JobView.model_validate(ended.json())

    assert (view.status, view.result) == (ServiceJobStatus.SUCCEEDED, RESULT)


def test_a_client_that_reconnects_is_sent_only_what_it_missed(
    served: Served,
) -> None:
    job_id = submitted(served)
    told(served, job_id)

    assert [frame.id for frame in frames(events(served, job_id, last="2"))] == ["3", "3"]
    assert [frame.id for frame in frames(events(served, job_id, query="?after=1"))] == [
        "2",
        "3",
        "3",
    ]
    assert [frame.event for frame in frames(events(served, job_id, last="3"))] == [FINISHED_EVENT]


@pytest.mark.parametrize("last", ["-1", "two"])
def test_a_last_event_that_is_no_number_from_0_is_refused(
    served: Served,
    last: str,
) -> None:
    job_id = submitted(served)
    answer = events(served, job_id, last=last)

    assert (answer.status, answer.json()["error"]) == (
        400,
        f"The last event sent is numbered from 0, as Last-Event-ID or after, not {last}.",
    )


def test_a_stream_follows_a_job_as_it_runs_and_ends_when_it_ends(
    served: Served,
) -> None:
    job_id = submitted(served)
    served.jobs.claim("runner-test")

    def run() -> None:
        for event in TOLD:
            time.sleep(0.05)
            served.jobs.append_event(job_id, event)

        served.jobs.finish(job_id, "runner-test", ServiceJobStatus.FAILED, refusal="{}")

    runner = threading.Thread(target=run)
    runner.start()
    answer = events(served, job_id)
    runner.join()

    assert [frame.event for frame in frames(answer)] == [JOB_EVENT] * 3 + [FINISHED_EVENT]
    assert JobView.model_validate(frames(answer)[-1].json()).status is ServiceJobStatus.FAILED


class Racing(SqlServiceJobRepository):
    """Jobs whose runner tells its last event and ends the job just after a stream read none."""

    def events(
        self,
        job_id: UUID,
        *,
        after: int = 0,
    ) -> tuple[ServiceJobEvent, ...]:
        read = super().events(job_id, after=after)
        held = self.get(job_id)

        if not read and held is not None and held.status is ServiceJobStatus.RUNNING:
            self.append_event(job_id, TOLD[-1])
            self.finish(job_id, "runner-test", ServiceJobStatus.SUCCEEDED, result="{}")

        return read


def test_an_event_told_just_before_its_job_ended_is_sent_before_the_end(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    path.touch()
    served = Served(path, principal=ERIS, jobs=Racing(open_repositories(path).database))
    job_id = submitted(served)
    served.jobs.claim("runner-test")

    for event in TOLD[:-1]:
        served.jobs.append_event(job_id, event)

    sent = frames(events(served, job_id))

    assert [(frame.id, frame.event) for frame in sent] == [
        ("1", JOB_EVENT),
        ("2", JOB_EVENT),
        ("3", JOB_EVENT),
        ("3", FINISHED_EVENT),
    ]
    assert sent[2].json() == {"type": "run_finished"}


def test_a_quiet_stream_says_it_is_still_there(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS, keep_alive_seconds=0.02)
    job_id = submitted(served)
    served.jobs.claim("runner-test")

    def end() -> None:
        time.sleep(0.3)
        served.jobs.finish(job_id, "runner-test", ServiceJobStatus.CANCELLED)

    ender = threading.Thread(target=end)
    ender.start()
    answer = events(served, job_id)
    ender.join()

    assert "still running" in [frame.comment for frame in frames(answer)]
    assert frames(answer)[-1].event == FINISHED_EVENT


def test_a_job_whose_events_are_streamed_is_not_audited(
    served: Served,
) -> None:
    job_id = submitted(served)
    told(served, job_id)
    before = list(served.audit.events)
    events(served, job_id)

    assert served.audit.events == before


# Who is sent them


def test_another_callers_events_are_streamed_to_who_may_read_runs(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    eris = Served(path, principal=ERIS)
    job_id = submitted(eris)
    told(eris, job_id)
    other = Served(path, principal=DISCORDIA)

    assert events(other, job_id).status == 200
    assert other.policy.asked == [("Discordia", Action.READ_RUNS, f"job {job_id}")]

    refused = Served(path, principal=DISCORDIA, policy=Refusing(Action.READ_RUNS))
    answer = events(refused, job_id)

    assert (answer.status, answer.json()["code"]) == (403, "permission_denied")


def test_restricted_events_are_streamed_only_to_who_may_read_restricted_and_told_first(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    eris = Served(path, principal=ERIS)
    job_id = submitted(eris, sensitivity="restricted")
    told(eris, job_id)
    refused = events(Served(path, principal=ERIS, policy=Refusing(Action.READ_RESTRICTED)), job_id)

    assert (refused.status, refused.json()["code"]) == (403, "permission_denied")
    assert "run_started" not in refused.body.decode()
    assert RUN_ID not in refused.body.decode()

    allowed = Served(path, principal=ERIS)

    assert len(frames(events(allowed, job_id))) == 4
    assert [(event.kind, event.resource) for event in allowed.audit.events] == [
        (AuditEventKind.RESTRICTED_READ, f"job {job_id}")
    ]


def test_restricted_events_are_refused_while_the_job_still_runs(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    job_id = submitted(Served(path, principal=ERIS), sensitivity="restricted")
    answer = events(Served(path, principal=ERIS, policy=Refusing(Action.READ_RESTRICTED)), job_id)

    assert answer.status == 403


def test_the_events_of_a_job_the_remote_does_not_have_are_not_found(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS)
    missing = events(served, MISSING)
    none = events(Served(tmp_path / "other.db", principal=ERIS, runs_jobs=False), MISSING)

    assert (missing.status, missing.json()["code"]) == (404, "not_found")
    assert (none.status, none.json()["error"]) == (404, NO_JOBS_MESSAGE)


def test_an_event_is_sent_on_one_line_whatever_it_holds() -> None:
    assert server_sent(JOB_EVENT, '{"a":\n"b"}', event_id=7) == (
        'id: 7\nevent: event\ndata: {"a": "b"}\n\n'
    )

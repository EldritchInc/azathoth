"""Tests of the routes a remote answers each call of the service API at (ADR 0127)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.api.calls import SERVICE_CALLS
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import (
    Action,
    AuditEventKind,
    Decision,
    OwnerOnlyPolicy,
    Principal,
    Seams,
)
from azathoth.remote.calling import CallerInstances
from azathoth.remote.server import JOB_CODE, RemoteServer, call_resource
from tests.remote.asgi import BEARER, Answer, call
from tests.remote.test_service_routes import GUEST, OWNER, ListAudit, Named

MISSING = UUID("c1070000-0000-4000-8000-000000000001")

ERIS = Principal(name="Eris", owner=True)


class Asking(OwnerOnlyPolicy):
    """The core's policy, noting every question it is asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, Action, str | None]] = []

    def decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> Decision:
        self.asked.append((principal.name, action, resource))

        return super().decide(principal, action, resource)


class Served:
    """A remote serving the service API over an SQLite database, and what its seams saw."""

    def __init__(
        self,
        path: Path,
        *,
        principal: Principal | None = OWNER,
        serves_calls: bool = True,
        policy: Asking | None = None,
        audit: ListAudit | None = None,
    ) -> None:
        sqlite3.connect(path).close()
        held = open_repositories(path)
        self.policy = policy if policy is not None else Asking()
        self.audit = audit if audit is not None else ListAudit()
        self.app = RemoteServer(
            workflows=held.workflows,
            tools=held.tools,
            benchmarks=held.benchmarks,
            content=held.content,
            production_states=held.production_states,
            portfolio=held.portfolio,
            seams=Seams(authenticator=Named(principal), policy=self.policy, audit=self.audit),
            accepts_restricted=False,
            environ={},
            instances=CallerInstances(held) if serves_calls else None,
        ).app()

    def call(
        self,
        name: str,
        body: object | None = None,
        *,
        authorization: str | None = BEARER,
    ) -> Answer:
        return call(self.app, "POST", f"/v1/calls/{name}", body=body, authorization=authorization)


@pytest.fixture
def served(
    tmp_path: Path,
) -> Iterator[Served]:
    yield Served(tmp_path / "azathoth.db", principal=ERIS)


# Answering calls


def test_a_call_is_answered_with_its_result_as_json(
    served: Served,
) -> None:
    answer = served.call("describe")

    assert answer.status == 200
    assert answer.json()["backend"] == "sqlite"
    assert answer.json()["api_stability"] == "stable"


def test_a_call_of_a_collection_takes_its_arguments_by_name(
    served: Served,
) -> None:
    listed = served.call("runs.list", {"workflow_id": str(MISSING), "limit": 5})
    refused = served.call("runs.list", {"workflow_id": str(MISSING), "limit": "five"})

    assert served.call("workflows.list").json() == []
    assert (listed.status, listed.json()["code"]) == (404, "not_found")
    assert (refused.status, refused.json()["code"]) == (400, "invalid_argument")
    assert refused.json()["error"].startswith(
        "These are not the arguments runs.list takes at limit:"
    )


def test_what_a_caller_makes_is_recorded_as_theirs(
    served: Served,
) -> None:
    created = served.call("benchmarks.create", {"name": "charts", "description": "Charts."})
    benchmark = created.json()["benchmark"]
    listed = served.call("benchmarks.list").json()

    assert created.status == 200
    assert benchmark["revision"]["author"] == {"name": "Eris", "email": None}
    assert [summary["id"] for summary in listed] == [benchmark["id"]]


def test_each_caller_is_recorded_as_themself(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    Served(path, principal=ERIS).call("benchmarks.create", {"name": "a", "description": "A."})
    other = Served(path, principal=Principal(name="Discordia", owner=True))
    other.call("benchmarks.create", {"name": "b", "description": "B."})

    authors = sorted(
        summary["revision"]["author"]["name"] for summary in other.call("benchmarks.list").json()
    )

    assert authors == ["Discordia", "Eris"]


# Refusing calls


def test_an_api_error_is_answered_with_its_status_and_code(
    served: Served,
) -> None:
    answer = served.call("workflows.get", {"workflow_id": str(MISSING)})

    assert answer.status == 404
    assert answer.json()["code"] == "not_found"
    assert str(MISSING) in answer.json()["error"]


def test_arguments_that_are_not_the_calls_are_refused_saying_where(
    served: Served,
) -> None:
    answer = served.call("workflows.get", {"workflow": str(MISSING)})

    assert answer.status == 400
    assert answer.json() == {
        "error": "These are not the arguments workflows.get takes at workflow: Extra inputs are "
        "not permitted.",
        "code": "invalid_argument",
        "kinds": ["invalid_argument", "error"],
    }


def test_a_call_the_service_api_does_not_have_is_not_found(
    served: Served,
) -> None:
    answer = served.call("workflows.fly")

    assert (answer.status, answer.json()) == (
        404,
        {"error": "The service API has no call named workflows.fly.", "code": "not_found"},
    )


@pytest.mark.parametrize(
    "name",
    [call.name for call in SERVICE_CALLS if not call.served],
)
def test_a_call_a_remote_never_serves_is_not_found(
    served: Served,
    name: str,
) -> None:
    answer = served.call(name)

    assert answer.status == 404
    assert answer.json() == {
        "error": f"A remote never serves {name}: it names this instance's own remotes, which a "
        "remote never holds.",
        "code": "not_found",
    }


@pytest.mark.parametrize(
    "name",
    [call.name for call in SERVICE_CALLS if call.job],
)
def test_a_job_is_not_run_while_the_request_waits(
    served: Served,
    name: str,
) -> None:
    answer = served.call(name)

    assert answer.status == 501
    assert answer.json() == {
        "error": f"{name} runs on the remote's workers, which this remote does not run jobs on "
        "yet.",
        "code": JOB_CODE,
    }


def test_a_remote_serving_only_the_protocol_says_so(
    tmp_path: Path,
) -> None:
    answer = Served(tmp_path / "azathoth.db", serves_calls=False).call("describe")

    assert (answer.status, answer.json()) == (
        404,
        {
            "error": "This remote serves only push, pull and status, not the service API.",
            "code": "not_found",
        },
    )


def test_a_call_needs_a_caller_the_remote_knows(
    tmp_path: Path,
) -> None:
    answer = Served(tmp_path / "azathoth.db", principal=None).call("describe", authorization=None)

    assert (answer.status, answer.json()["code"]) == (401, "unauthenticated")


def test_a_call_is_only_ever_posted(
    served: Served,
) -> None:
    assert call(served.app, "GET", "/v1/calls/describe").status == 405


# Asking the policy


def test_a_call_asks_each_of_its_actions_about_what_it_names(
    served: Served,
) -> None:
    served.call("tools.usage", {"tool_id": str(MISSING)})

    assert served.policy.asked == [
        ("Eris", Action.READ_CATALOG, f"tool {MISSING}"),
        ("Eris", Action.READ_RUNS, f"tool {MISSING}"),
    ]


def test_a_call_naming_nothing_asks_about_nothing(
    served: Served,
) -> None:
    served.call("workflows.list")

    assert served.policy.asked == [("Eris", Action.READ_CATALOG, None)]


def test_a_caller_the_policy_refuses_is_told_why_nothing_runs_and_the_refusal_is_audited(
    tmp_path: Path,
) -> None:
    refused = Served(tmp_path / "azathoth.db", principal=GUEST)
    answer = refused.call("benchmarks.create", {"name": "charts", "description": "Charts."})
    owner = Served(tmp_path / "azathoth.db", principal=ERIS)

    assert answer.status == 403
    assert answer.json() == {
        "error": "guest may not edit benchmark on this remote: only its owner may.",
        "code": "permission_denied",
    }
    assert [event.kind for event in refused.audit.events] == [AuditEventKind.REQUEST_DENIED]
    assert refused.audit.events[0].resource == "POST /v1/calls/benchmarks.create"
    assert owner.call("benchmarks.list").json() == []


def test_the_resource_a_call_names_is_its_kind_and_id() -> None:
    calls = {each.name: each for each in SERVICE_CALLS}

    assert call_resource(calls["workflows.get"], {"workflow_id": MISSING}) == f"workflow {MISSING}"
    assert call_resource(calls["portfolio.add"], {"identifier": "bedrock/x"}) == "model bedrock/x"
    assert call_resource(calls["runs.list"], {"workflow_id": None}) is None
    assert call_resource(calls["workflows.list"], {}) is None

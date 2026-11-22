"""Tests that a remote tells its audit what it does before it does it (ADR 0136)."""

from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.api.calls import service_call
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import Action, AuditEvent, AuditEventKind, Seams
from azathoth.remote.server import (
    AUDIT_UNAVAILABLE_CODE,
    AUDIT_UNAVAILABLE_MESSAGE,
    RemoteServer,
    audit_kinds,
)
from azathoth.sensitivity import Sensitivity
from tests.remote.asgi import call
from tests.remote.test_call_routes import ERIS, Served
from tests.remote.test_closure import PARENT
from tests.remote.test_conditions import EXAMPLES, Refusing, benchmark_with_a_case
from tests.remote.test_receiving import Bare, bundle, local_with_history
from tests.remote.test_service_routes import GUEST, OWNER, ListAudit, Named

MISSING = UUID("c1090000-0000-4000-8000-000000000001")


class Watching(ListAudit):
    """An audit that keeps what it is told, and what was true when it was told."""

    def __init__(
        self,
        look: Callable[[], object],
    ) -> None:
        super().__init__()
        self.look = look
        self.seen: list[object] = []

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        super().record(event)
        self.seen.append(self.look())


class Broken(ListAudit):
    """An audit that cannot be told anything but a refusal or a failure."""

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        if event.kind not in (AuditEventKind.REQUEST_DENIED, AuditEventKind.REQUEST_FAILED):
            raise ConnectionError("The audit's database is down.")

        super().record(event)


def kinds(
    audit: ListAudit,
) -> list[AuditEventKind]:
    return [event.kind for event in audit.events]


# What a call tells


def test_a_call_that_only_reads_tells_the_audit_nothing(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS)
    served.call("workflows.list")
    served.call("benchmarks.list")

    assert served.audit.events == []


def test_a_change_is_told_before_it_is_made_naming_who_what_and_the_call(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    audit = Watching(lambda: len(open_repositories(path).benchmarks.datasets()))
    served = Served(path, principal=ERIS, audit=audit)

    created = served.call("benchmarks.create", {"name": "charts", "description": "Charts."})
    (event,) = audit.events

    assert created.status == 200
    assert (event.kind, event.principal, event.resource, event.detail) == (
        AuditEventKind.BENCHMARK_CREATED,
        "Eris",
        None,
        "benchmarks.create",
    )
    assert audit.seen == [0]


def test_a_change_to_one_thing_names_it(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS)
    benchmark_id = benchmark_with_a_case(served, None)
    (_, added) = served.audit.events

    assert added.kind is AuditEventKind.BENCHMARK_CASE_ADDED
    assert added.resource == f"benchmark {benchmark_id}"


def test_a_change_that_then_fails_is_told_to_have_failed(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS)
    answer = served.call(
        "benchmarks.remove_case",
        {"benchmark_id": str(MISSING), "case_id": str(MISSING)},
    )

    assert (answer.status, answer.json()["code"]) == (404, "not_found")
    assert kinds(served.audit) == [
        AuditEventKind.BENCHMARK_CASE_REMOVED,
        AuditEventKind.REQUEST_FAILED,
    ]
    (told, failed) = served.audit.events

    assert failed.resource == told.resource == f"benchmark {MISSING}"
    assert failed.detail == "benchmarks.remove_case: not_found"
    assert failed.principal == "Eris"


def test_importing_a_process_tool_tells_both_imports(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS)
    served.call("tools.import_document", {"document": (EXAMPLES / "word-count.json").read_text()})
    served.call(
        "tools.import_document",
        {"document": (EXAMPLES / "word-count-process.json").read_text()},
    )

    assert kinds(served.audit) == [
        AuditEventKind.TOOL_IMPORTED,
        AuditEventKind.TOOL_IMPORTED,
        AuditEventKind.PROCESS_TOOL_IMPORTED,
    ]


def test_reading_restricted_data_is_told_before_it_is_sent(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS)
    restricted = benchmark_with_a_case(served, Sensitivity.RESTRICTED)
    open_ = benchmark_with_a_case(served, None)
    before = len(served.audit.events)

    served.call("benchmarks.get", {"benchmark_id": open_})
    served.call("benchmarks.get", {"benchmark_id": restricted})
    (read,) = served.audit.events[before:]

    assert (read.kind, read.resource, read.detail) == (
        AuditEventKind.RESTRICTED_READ,
        f"benchmark {restricted}",
        "benchmarks.get",
    )


def test_a_restricted_read_the_policy_refuses_is_told_as_a_refusal_only(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    restricted = benchmark_with_a_case(Served(path, principal=ERIS), Sensitivity.RESTRICTED)
    refused = Served(path, principal=ERIS, policy=Refusing(Action.READ_RESTRICTED))

    refused.call("benchmarks.get", {"benchmark_id": restricted})

    assert kinds(refused.audit) == [AuditEventKind.REQUEST_DENIED]


@pytest.mark.parametrize(
    ("name", "asked", "told"),
    [
        ("tools.import_document", [Action.IMPORT_TOOL], [AuditEventKind.TOOL_IMPORTED]),
        (
            "tools.import_document",
            [Action.IMPORT_TOOL, Action.IMPORT_PROCESS_TOOL],
            [AuditEventKind.TOOL_IMPORTED, AuditEventKind.PROCESS_TOOL_IMPORTED],
        ),
        ("benchmarks.get", [Action.READ_CATALOG], []),
        ("benchmarks.get", [Action.READ_RESTRICTED], [AuditEventKind.RESTRICTED_READ]),
        ("workflows.list", [Action.READ_CATALOG], []),
    ],
)
def test_a_call_tells_each_kind_it_may_record_whose_action_it_asked(
    name: str,
    asked: list[Action],
    told: list[AuditEventKind],
) -> None:
    assert list(audit_kinds(service_call(name), asked)) == told


# An audit that cannot be told


def test_a_change_the_audit_cannot_be_told_of_is_refused_and_not_made(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    served = Served(path, principal=ERIS, audit=Broken())
    answer = served.call("benchmarks.create", {"name": "charts", "description": "Charts."})

    assert answer.status == 503
    assert answer.json() == {"error": AUDIT_UNAVAILABLE_MESSAGE, "code": AUDIT_UNAVAILABLE_CODE}
    assert AUDIT_UNAVAILABLE_MESSAGE == (
        "This remote could not tell its audit what was asked, so it did nothing; its log says why."
    )
    assert AUDIT_UNAVAILABLE_CODE == "audit_unavailable"
    assert open_repositories(path).benchmarks.datasets() == ()


def test_restricted_data_the_audit_cannot_be_told_of_is_not_sent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    restricted = benchmark_with_a_case(Served(path, principal=ERIS), Sensitivity.RESTRICTED)
    answer = Served(path, principal=ERIS, audit=Broken()).call(
        "benchmarks.get",
        {"benchmark_id": restricted},
    )

    assert (answer.status, answer.json()["code"]) == (503, AUDIT_UNAVAILABLE_CODE)
    assert "412" not in answer.body.decode()


def test_a_refusal_is_answered_even_when_the_audit_cannot_be_told_of_it(
    tmp_path: Path,
) -> None:
    class Down(ListAudit):
        def record(
            self,
            event: AuditEvent,
        ) -> None:
            raise ConnectionError("The audit's database is down.")

    served = Served(tmp_path / "azathoth.db", principal=GUEST, audit=Down())
    answer = served.call("benchmarks.create", {"name": "charts", "description": "Charts."})

    assert (answer.status, answer.json()["code"]) == (403, "permission_denied")


# The protocol's routes


def protocol(
    audit: ListAudit,
    *,
    policy: Refusing | None = None,
) -> tuple[object, Bare]:
    held = Bare()
    app = RemoteServer(
        workflows=held.workflows,
        tools=held.tools,
        benchmarks=held.benchmarks,
        content=held.content,
        production_states=held.production_states,
        portfolio=held.portfolio,
        seams=Seams(
            authenticator=Named(OWNER),
            policy=policy if policy is not None else Refusing(),
            audit=audit,
        ),
        accepts_restricted=False,
        environ={},
    ).app()

    return app, held


def test_a_push_the_audit_cannot_be_told_of_receives_nothing() -> None:
    app, held = protocol(Broken())
    sent = bundle(local_with_history(), PARENT)
    answer = call(app, "POST", "/v1/push", raw=sent.model_dump_json().encode())

    assert answer.status == 503
    assert answer.json() == {"error": AUDIT_UNAVAILABLE_MESSAGE}
    assert held.workflows.specifications() == ()


def test_a_push_is_told_before_anything_is_received() -> None:
    watched: list[Bare] = []
    audit = Watching(lambda: len(watched[0].workflows.specifications()))
    app, held = protocol(audit)
    watched.append(held)
    sent = bundle(local_with_history(), PARENT)

    answer = call(app, "POST", "/v1/push", raw=sent.model_dump_json().encode())

    assert answer.status == 200
    assert kinds(audit) == [AuditEventKind.PUSH]
    assert audit.seen == [0]
    assert audit.events[0].detail == f"Offered {len(sent.revisions)} revisions."


def test_a_read_the_audit_cannot_be_told_of_is_not_sent() -> None:
    app, _ = protocol(Broken())
    answer = call(app, "GET", "/v1/capabilities")

    assert (answer.status, answer.json()) == (503, {"error": AUDIT_UNAVAILABLE_MESSAGE})


# Installing the standard tools


def test_the_standard_tools_are_installed_through_a_remote_asked_and_told_as_such(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS)
    answer = served.call("tools.install_standard")

    assert answer.status == 200
    assert all(tool["installed"] for tool in answer.json())
    assert served.policy.asked == [("Eris", Action.INSTALL_STANDARD_TOOLS, None)]
    assert [(event.kind, event.detail) for event in served.audit.events] == [
        (AuditEventKind.STANDARD_TOOLS_INSTALLED, "tools.install_standard")
    ]


def test_installing_the_standard_tools_is_refused_to_a_caller_the_policy_refuses(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    answer = Served(path, principal=GUEST).call("tools.install_standard")

    assert (answer.status, answer.json()["code"]) == (403, "permission_denied")
    assert Served(path, principal=ERIS).call("tools.list").json() == []

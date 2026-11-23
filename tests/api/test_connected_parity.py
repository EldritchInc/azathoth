"""Tests that a connected instance answers as a local one over the same database does (ADR 0137).

Each test makes what it reads through a remote, then reads it through both a
local instance and the connected one, and requires the same answer, or the
same error with the same message.
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from azathoth import api
from azathoth.api.connected import ConnectedInstance, Instance
from azathoth.api.models import RunInput
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import Action, Principal
from azathoth.sensitivity import Sensitivity
from tests.remote.asgi import AsgiHttp, AsgiResponse
from tests.remote.test_call_audit import Broken
from tests.remote.test_call_routes import ERIS, Asking, Served
from tests.remote.test_conditions import EXAMPLES, Refusing
from tests.remote.test_listings import Seeing
from tests.remote.test_service_routes import GUEST, ListAudit

URL = "http://remote.test"

WORKFLOWS = EXAMPLES.parent / "workflows"

MISSING = UUID("c1130000-0000-4000-8000-000000000001")


class Pair:
    """One database, opened locally and served by a remote, to the same caller."""

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = path
        self.served = Served(path, principal=ERIS)
        self.http = AsgiHttp(self.served.app)
        self.connected = api.connect(URL, token="azr_test", http=self.http)
        self.local = api.open(path, author="Eris")

    def close(self) -> None:
        self.connected.close()
        self.local.close()

    def through(
        self,
        *,
        principal: Principal | None = ERIS,
        policy: Asking | None = None,
        audit: ListAudit | None = None,
    ) -> ConnectedInstance:
        """Return an instance connected to the same database, served another way."""

        served = Served(
            self.path,
            principal=principal,
            policy=policy,
            audit=audit,
        )

        return api.connect(URL, token="azr_test", http=AsgiHttp(served.app))

    def both(
        self,
        read: Callable[[Instance], Any],
    ) -> tuple[object, object]:
        """Return what a read answers, or the error it raises, locally and connected."""

        return answered(read, self.local), answered(read, self.connected)


class Keeping(AsgiHttp):
    """An in-process HTTP client that keeps every answer's body too."""

    def __init__(
        self,
        app: Any,
    ) -> None:
        super().__init__(app)
        self.answers: list[bytes] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> AsgiResponse:
        answer = super().request(method, url, content=content, headers=headers)
        self.answers.append(answer.content)

        return answer


@dataclass(frozen=True)
class Raised:
    """The kind and message of an error a read raised."""

    kind: type[api.ApiError]
    message: str


def answered(
    read: Callable[[Instance], Any],
    instance: Instance,
) -> object:
    """Return what a read answers, or the kind and message of the error it raises."""

    try:
        return read(instance)
    except api.ApiError as error:
        return Raised(type(error), str(error))


@pytest.fixture
def pair(
    tmp_path: Path,
) -> Iterator[Pair]:
    made = Pair(tmp_path / "azathoth.db")

    try:
        yield made
    finally:
        made.close()


def document(
    path: Path,
) -> str:
    return path.read_text(encoding="utf-8")


def catalog(
    instance: Instance,
) -> tuple[UUID, UUID, UUID]:
    """Import two tools and a workflow that uses both, make a benchmark with a case, and
    return the IDs of the workflow, the Python tool and the benchmark."""

    tool = instance.tools.import_document(document(EXAMPLES / "word-count.json"))
    instance.tools.import_document(document(EXAMPLES / "word-count-process.json"))
    workflow = instance.workflows.import_document(document(WORKFLOWS / "word-count-messages.json"))
    benchmark = instance.benchmarks.create("charts", "Charts.")
    instance.benchmarks.add_case(
        benchmark.benchmark.id,
        input=RunInput(payload={"chart": "412"}),
        comparison="exact",
        expected="fine",
    )

    return workflow.workflow.id, tool.tool.id, benchmark.benchmark.id


# The same answers


def test_what_is_made_through_a_remote_reads_the_same_locally_and_connected(
    pair: Pair,
) -> None:
    workflow_id, tool_id, benchmark_id = catalog(pair.connected)
    reads: list[Callable[[Instance], Any]] = [
        lambda instance: instance.describe(),
        lambda instance: instance.workflows.list(),
        lambda instance: instance.workflows.get(workflow_id),
        lambda instance: instance.workflows.history(workflow_id, limit=5),
        lambda instance: instance.workflows.check(document(WORKFLOWS / "countdown.json")),
        lambda instance: instance.tools.list(),
        lambda instance: instance.tools.get(tool_id, "1.0.0"),
        lambda instance: instance.tools.history(tool_id),
        lambda instance: instance.tools.usage(tool_id),
        lambda instance: instance.benchmarks.list(),
        lambda instance: instance.benchmarks.get(benchmark_id),
        lambda instance: instance.benchmarks.history(benchmark_id),
        lambda instance: instance.goals.list(),
        lambda instance: instance.portfolio.list(),
    ]

    for read in reads:
        local, connected = pair.both(read)

        assert not isinstance(local, Raised), local
        assert connected == local


def test_what_is_made_through_a_remote_is_the_callers(
    pair: Pair,
) -> None:
    workflow_id, tool_id, benchmark_id = catalog(pair.connected)

    eris = api.Author(name="Eris", email=None)

    assert pair.local.workflows.get(workflow_id).revision.author == eris
    assert pair.local.tools.get(tool_id, "1.0.0").revision.author == eris
    assert pair.local.benchmarks.get(benchmark_id).revision.author == eris


@pytest.mark.parametrize(
    "read",
    [
        lambda instance: instance.workflows.get(MISSING),
        lambda instance: instance.workflows.history(MISSING, limit=0),
        lambda instance: instance.tools.get(MISSING, "1.0.0"),
        lambda instance: instance.benchmarks.get(MISSING, revision=3),
        lambda instance: instance.runs.get(MISSING),
        lambda instance: instance.workflows.import_document('{"metadata": {}}'),
        lambda instance: instance.portfolio.remove("bedrock/no-such-model"),
    ],
    ids=[
        "missing-workflow",
        "limit",
        "missing-tool",
        "missing-revision",
        "missing-run",
        "invalid-document",
        "unknown-model",
    ],
)
def test_an_error_is_the_same_kind_and_message_locally_and_connected(
    pair: Pair,
    read: Callable[[Instance], Any],
) -> None:
    local, connected = pair.both(read)

    assert isinstance(local, Raised)
    assert connected == local


# What a remote's policy and audit refuse


def test_a_caller_the_policy_refuses_changes_nothing_and_is_told_why(
    pair: Pair,
) -> None:
    with (
        pair.through(principal=GUEST) as guest,
        pytest.raises(api.PermissionDeniedError) as caught,
    ):
        guest.benchmarks.create("charts", "Charts.")

    assert str(caught.value) == "guest may not edit benchmark on this remote: only its owner may."
    assert pair.local.benchmarks.list() == ()


def test_a_listing_through_a_remote_leaves_out_what_its_policy_refuses(
    pair: Pair,
) -> None:
    seen = pair.connected.benchmarks.create("seen", "Seen.").benchmark.id
    pair.connected.benchmarks.create("hidden", "Hidden.")

    with pair.through(policy=Seeing(f"benchmark {seen}")) as seeing:
        listed = seeing.benchmarks.list()

    assert [summary.id for summary in listed] == [seen]
    assert len(pair.local.benchmarks.list()) == 2


def test_restricted_data_the_policy_refuses_is_not_sent(
    pair: Pair,
) -> None:
    benchmark = pair.connected.benchmarks.create("charts", "Charts.").benchmark.id
    pair.connected.benchmarks.add_case(
        benchmark,
        input=RunInput(payload={"chart": "412"}),
        comparison="exact",
        expected="fine",
        sensitivity=Sensitivity.RESTRICTED,
    )
    http = Keeping(Served(pair.path, principal=ERIS, policy=Refusing(Action.READ_RESTRICTED)).app)

    with (
        api.connect(URL, token="azr_test", http=http) as refused,
        pytest.raises(api.PermissionDeniedError),
    ):
        refused.benchmarks.get(benchmark)

    (answer,) = http.answers

    assert b"412" not in answer
    assert json.loads(answer)["code"] == "permission_denied"


def test_a_remote_whose_audit_is_down_changes_nothing_and_may_answer_later(
    pair: Pair,
) -> None:
    with (
        pair.through(audit=Broken()) as down,
        pytest.raises(api.RemoteUnavailableError) as caught,
    ):
        down.benchmarks.create("charts", "Charts.")

    assert (caught.value.status, caught.value.refusal) == (503, "audit_unavailable")
    assert pair.local.benchmarks.list() == ()


def test_a_token_the_remote_does_not_know_is_refused(
    pair: Pair,
) -> None:
    with (
        pair.through(principal=None) as unknown,
        pytest.raises(api.RemoteRefusedError) as caught,
    ):
        unknown.workflows.list()

    assert (caught.value.status, caught.value.refusal) == (401, "unauthenticated")


def test_what_a_remote_tells_its_audit_is_the_same_for_a_connected_caller(
    pair: Pair,
) -> None:
    catalog(pair.connected)

    assert [event.detail for event in pair.served.audit.events] == [
        "tools.import_document",
        "tools.import_document",
        "tools.import_document",
        "workflows.import_document",
        "benchmarks.create",
        "benchmarks.add_case",
    ]
    assert {event.principal for event in pair.served.audit.events} == {"Eris"}
    assert len(open_repositories(pair.path).benchmarks.datasets()) == 1

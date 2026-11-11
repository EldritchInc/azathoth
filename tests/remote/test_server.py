"""Tests for the HTTP server a remote serves its protocol with (ADR 0124)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from azathoth import __version__
from azathoth.persistence.database import SCHEMA_VERSION
from azathoth.remote import (
    MAX_CONTENT_BYTES,
    SENSITIVITY_HEADER,
    Action,
    AuditEvent,
    AuditEventKind,
    Decision,
    MissingRequest,
    NoAuditSink,
    OwnerOnlyPolicy,
    Principal,
    PullRequest,
    PushBundle,
    ReceiveReport,
    Seams,
    SQLiteRemoteTokenRepository,
    TokenAuthenticator,
    restricted_refusal,
)
from azathoth.remote.server import UNKNOWN_TOKEN_MESSAGE, RemoteServer
from azathoth.sensitivity import Sensitivity
from tests.remote.test_closure import (
    BENCHMARK,
    CHILD,
    PARENT,
    PARENT_ID,
    Instance,
    child,
    parent,
)
from tests.remote.test_pulling import with_benchmark
from tests.remote.test_receiving import (
    CHART,
    CHART_BYTES,
    Bare,
    bundle,
    charts,
    local_with_history,
)

NOW = datetime(2026, 11, 10, 23, 0, tzinfo=UTC)


class ListAudit:
    """An audit that keeps what it is told."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(
        self,
        event: AuditEvent,
    ) -> None:
        self.events.append(event)

    def kinds(
        self,
    ) -> list[AuditEventKind]:
        return [event.kind for event in self.events]


class GuestAuthenticator:
    """An authenticator that names everyone a guest, so the core policy refuses them."""

    def authenticate(
        self,
        authorization: str | None,
    ) -> Principal | None:
        return Principal(name="guest")


class Remote:
    """One remote served in-process, its token, and what its audit was told."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        held: Instance | None = None,
        accepts_restricted: bool = False,
        guest: bool = False,
    ) -> None:
        tokens = SQLiteRemoteTokenRepository(tmp_path / "remote.db")
        self.token = tokens.create("laptop").secret
        self.held = held if held is not None else Bare()
        self.content = self.held.content
        self.audit = ListAudit()
        server = RemoteServer(
            workflows=self.held.workflows,
            tools=self.held.tools,
            benchmarks=self.held.benchmarks,
            content=self.content,
            seams=Seams(
                authenticator=GuestAuthenticator() if guest else TokenAuthenticator(tokens),
                policy=OwnerOnlyPolicy(),
                audit=self.audit,
            ),
            accepts_restricted=accepts_restricted,
            clock=lambda: NOW,
        )
        self.client = TestClient(server.app())

    def headers(
        self,
        **more: str,
    ) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", **more}


@pytest.fixture
def remote(
    tmp_path: Path,
) -> Remote:
    return Remote(tmp_path)


# Reaching the remote


def test_health_needs_no_token(
    remote: Remote,
) -> None:
    answer = remote.client.get("/health")

    assert (answer.status_code, answer.json()) == (200, {"status": "ok"})
    assert remote.audit.events == []


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer azr_unknown"}, {"Authorization": "Basic abc"}],
    ids=["none", "unknown", "basic"],
)
def test_a_request_without_a_known_token_is_refused_and_audited(
    remote: Remote,
    headers: dict[str, str],
) -> None:
    answer = remote.client.get("/v1/capabilities", headers=headers)

    assert (answer.status_code, answer.json()) == (401, {"error": UNKNOWN_TOKEN_MESSAGE})
    assert remote.audit.events == [
        AuditEvent(
            kind=AuditEventKind.REQUEST_DENIED,
            occurred_at=NOW,
            resource="GET /v1/capabilities",
            detail=UNKNOWN_TOKEN_MESSAGE,
        )
    ]
    assert UNKNOWN_TOKEN_MESSAGE == (
        "This remote does not know the token given. Send one its owner created with "
        "`azathoth remote token create`, as `Authorization: Bearer <TOKEN>`."
    )


def test_a_caller_the_policy_refuses_is_told_why_and_audited(
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path, guest=True)

    answer = remote.client.post("/v1/pull", json={"roots": []})

    assert answer.status_code == 403
    assert answer.json() == {"error": "guest may not pull on this remote: only its owner may."}
    assert remote.audit.events[0].principal == "guest"
    assert remote.audit.kinds() == [AuditEventKind.REQUEST_DENIED]


def test_capabilities_say_what_the_remote_is(
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path, accepts_restricted=True)

    answer = remote.client.get("/v1/capabilities", headers=remote.headers())

    assert answer.json() == {
        "protocol": 1,
        "azathoth_version": __version__,
        "schema_version": SCHEMA_VERSION,
        "edition": "community",
        "plugins": {},
        "accepts_restricted": True,
    }
    assert remote.audit.events == [
        AuditEvent(kind=AuditEventKind.CAPABILITIES_READ, occurred_at=NOW, principal="laptop")
    ]


# Have and want


def test_the_remote_says_which_offered_revisions_and_content_it_lacks(
    tmp_path: Path,
) -> None:
    local = local_with_history()
    remote = Remote(tmp_path)
    remote.content.put(CHART_BYTES)
    sent = bundle(local, PARENT)
    remote.client.post(
        "/v1/push",
        headers=remote.headers(),
        content=PushBundle(revisions=sent.revisions[:3]).model_dump_json(),
    )
    offered = MissingRequest(
        lineages=tuple(dict.fromkeys(record.lineage for record in sent.revisions)),
        revisions=tuple(record.revision_digest for record in sent.revisions),
        content=(CHART.digest, "f" * 64),
    )

    answer = remote.client.post(
        "/v1/missing",
        headers=remote.headers(),
        content=offered.model_dump_json(),
    )

    assert answer.status_code == 200
    assert answer.json() == {
        "revisions": [record.revision_digest for record in sent.revisions[3:]],
        "content": ["f" * 64],
    }


def test_a_malformed_request_is_refused_saying_where(
    remote: Remote,
) -> None:
    answer = remote.client.post(
        "/v1/missing",
        headers=remote.headers(),
        content='{"revisions": ["not a digest"]}',
    )

    assert answer.status_code == 400
    assert answer.json() == {
        "error": "This request is not a MissingRequest at revisions.0: String should match "
        "pattern '^[0-9a-f]{64}$'."
    }

    unparsed = remote.client.post("/v1/missing", headers=remote.headers(), content="{")

    assert unparsed.status_code == 400
    assert unparsed.json()["error"].startswith("This request is not a MissingRequest: ")


# Content


def test_content_is_kept_and_read_back(
    remote: Remote,
) -> None:
    put = remote.client.put(
        f"/v1/content/{CHART.digest}",
        headers=remote.headers(),
        content=CHART_BYTES,
    )
    got = remote.client.get(f"/v1/content/{CHART.digest}", headers=remote.headers())

    assert (put.status_code, put.json()) == (201, {"digest": CHART.digest})
    assert (got.status_code, got.content) == (200, CHART_BYTES)
    assert got.headers["content-type"] == "application/octet-stream"
    assert remote.audit.events == [
        AuditEvent(
            kind=AuditEventKind.CONTENT_READ,
            occurred_at=NOW,
            principal="laptop",
            resource=CHART.digest,
        )
    ]


def test_content_not_held_is_not_found(
    remote: Remote,
) -> None:
    answer = remote.client.get(f"/v1/content/{'f' * 64}", headers=remote.headers())

    assert (answer.status_code, answer.json()) == (
        404,
        {"error": f"This remote holds no content {'f' * 64}."},
    )


def test_a_route_naming_no_digest_is_refused(
    remote: Remote,
) -> None:
    answer = remote.client.get("/v1/content/chart.pdf", headers=remote.headers())

    assert (answer.status_code, answer.json()) == (
        400,
        {"error": "'chart.pdf' is not a content digest."},
    )


def test_content_that_is_not_its_digest_is_refused(
    remote: Remote,
) -> None:
    answer = remote.client.put(
        f"/v1/content/{CHART.digest}",
        headers=remote.headers(),
        content=b"other",
    )

    assert answer.status_code == 422
    assert answer.json()["error"].startswith(f"Content sent as {CHART.digest} is ")
    assert not remote.content.contains(CHART.digest)


@pytest.mark.parametrize("streamed", [False, True], ids=["declared", "streamed"])
def test_content_larger_than_a_remote_accepts_is_refused_before_it_is_read(
    remote: Remote,
    streamed: bool,
) -> None:
    large = b"x" * (MAX_CONTENT_BYTES + 1)
    body = iter([large[:MAX_CONTENT_BYTES], large[MAX_CONTENT_BYTES:]]) if streamed else large

    answer = remote.client.put(f"/v1/content/{'f' * 64}", headers=remote.headers(), content=body)

    assert (answer.status_code, answer.json()) == (
        413,
        {"error": f"Content {'f' * 64} is larger than this remote accepts, 10485760 bytes."},
    )


@pytest.mark.parametrize("accepts", [False, True], ids=["refused", "accepted"])
def test_restricted_content_needs_a_remote_that_accepts_it(
    tmp_path: Path,
    accepts: bool,
) -> None:
    remote = Remote(tmp_path, accepts_restricted=accepts)

    answer = remote.client.put(
        f"/v1/content/{CHART.digest}",
        headers=remote.headers(**{SENSITIVITY_HEADER: "restricted"}),
        content=CHART_BYTES,
    )

    if accepts:
        assert answer.status_code == 201
        return

    assert (answer.status_code, answer.json()) == (
        403,
        {"error": restricted_refusal(f"Content {CHART.digest} is restricted")},
    )
    assert remote.audit.kinds() == [AuditEventKind.REQUEST_DENIED]


def test_an_unknown_label_is_refused(
    remote: Remote,
) -> None:
    answer = remote.client.put(
        f"/v1/content/{CHART.digest}",
        headers=remote.headers(**{SENSITIVITY_HEADER: "secret"}),
        content=CHART_BYTES,
    )

    assert (answer.status_code, answer.json()) == (
        400,
        {"error": "X-Azathoth-Sensitivity 'secret' is not public, internal or restricted."},
    )


# Pushing


def push(
    remote: Remote,
    sent: PushBundle,
) -> tuple[int, dict[str, object]]:
    answer = remote.client.post(
        "/v1/push",
        headers=remote.headers(),
        content=sent.model_dump_json(),
    )

    return answer.status_code, answer.json()


def test_a_push_is_received_reported_and_audited(
    remote: Remote,
) -> None:
    sent = bundle(local_with_history(), PARENT)

    status, report = push(remote, sent)

    assert status == 200
    assert len(ReceiveReport.model_validate(report).received) == 5
    assert remote.held.workflows.lineage(PARENT_ID)[-1].revision_digest == (
        sent.revisions[-1].revision_digest
    )
    (event,) = remote.audit.events

    assert event.kind is AuditEventKind.PUSH
    assert event.principal == "laptop"
    assert event.detail == "Received 5 revisions; 0 already held."
    assert event.resource is not None
    assert event.resource.startswith("tool ")

    again = push(remote, sent)

    assert again == (200, ReceiveReport(already_held=5).model_dump(mode="json"))


def test_a_diverged_push_conflicts(
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    theirs.workflows.save(parent())
    theirs.workflows.save(parent("Counts differently."))
    remote = Remote(tmp_path, held=theirs)

    status, answer = push(remote, bundle(local_with_history(), PARENT))

    assert status == 409
    assert str(answer["error"]).startswith(f"Workflow {PARENT_ID} has diverged: ")
    assert str(answer["error"]).endswith(" Pull first, then push again.")
    assert remote.audit.events == []


def test_a_push_of_restricted_data_is_refused_unless_the_remote_accepts_it(
    tmp_path: Path,
) -> None:
    refusing = Remote(tmp_path)
    sent = bundle(charts(Sensitivity.RESTRICTED), BENCHMARK)

    assert push(refusing, sent) == (
        403,
        {"error": restricted_refusal("This push carries restricted data")},
    )

    (tmp_path / "accepting").mkdir()
    accepting = Remote(tmp_path / "accepting", accepts_restricted=True)
    accepting.content.put(CHART_BYTES)

    assert push(accepting, sent)[0] == 200


def test_a_push_the_checks_refuse_is_unprocessable(
    remote: Remote,
) -> None:
    status, answer = push(remote, bundle(charts(None), BENCHMARK))

    assert status == 422
    assert str(answer["error"]).startswith(f"Content {CHART.digest}, which revision ")


def test_a_push_of_another_protocol_is_refused_naming_both(
    remote: Remote,
) -> None:
    status, answer = push(remote, PushBundle(protocol=2))

    assert (status, answer) == (
        400,
        {
            "error": "The client speaks remote protocol 2, and this Azathoth speaks remote "
            "protocol 1; run versions of Azathoth that speak the same protocol on both."
        },
    )


# Pulling


def test_a_pull_sends_the_bundle_asked_for_and_is_audited(
    tmp_path: Path,
) -> None:
    held = with_benchmark(local_with_history(), Sensitivity.RESTRICTED)
    remote = Remote(tmp_path, held=held)

    answer = remote.client.post(
        "/v1/pull",
        headers=remote.headers(),
        content=PullRequest(roots=(PARENT, BENCHMARK)).model_dump_json(),
    )
    body = answer.json()

    assert answer.status_code == 200
    assert [record["lineage"]["kind"] for record in body["bundle"]["revisions"]] == [
        "tool",
        "tool",
        "workflow",
        "workflow",
        "workflow",
    ]
    assert body["withheld"] == [BENCHMARK.model_dump(mode="json")]
    (event,) = remote.audit.events

    assert event.kind is AuditEventKind.PULL
    assert event.resource == f"{PARENT}, {BENCHMARK}"
    assert event.detail == "Sent 5 revisions; withheld 1."


def test_a_pull_of_another_protocol_is_refused(
    remote: Remote,
) -> None:
    answer = remote.client.post(
        "/v1/pull",
        headers=remote.headers(),
        content=PullRequest(protocol=3, roots=(CHILD,)).model_dump_json(),
    )

    assert answer.status_code == 400
    assert answer.json()["error"].startswith("The client speaks remote protocol 3,")


# Policies by resource


class ChildOnlyPolicy:
    """A plugin policy that lets its owner push and pull only the child workflow."""

    edition = "test"

    def decide(
        self,
        principal: Principal,
        action: Action,
        resource: str | None,
    ) -> Decision:
        if action in (Action.PUSH, Action.PULL) and resource not in (None, str(CHILD)):
            return Decision(allowed=False, reason=f"Only {CHILD} may travel here.")

        return Decision(allowed=True)


def test_a_policy_decides_each_lineage_pushed_and_pulled(
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path)
    server = RemoteServer(
        workflows=remote.held.workflows,
        tools=remote.held.tools,
        benchmarks=remote.held.benchmarks,
        content=remote.content,
        seams=Seams(
            authenticator=TokenAuthenticator(SQLiteRemoteTokenRepository(tmp_path / "remote.db")),
            policy=ChildOnlyPolicy(),
            audit=NoAuditSink(),
        ),
        accepts_restricted=False,
    )
    client = TestClient(server.app())
    local = local_with_history()

    allowed = client.post(
        "/v1/push",
        headers=remote.headers(),
        content=PushBundle(revisions=bundle(local, CHILD).revisions).model_dump_json(),
    )
    refused = client.post(
        "/v1/push",
        headers=remote.headers(),
        content=bundle(local, PARENT).model_dump_json(),
    )

    assert allowed.status_code == 200
    assert (refused.status_code, refused.json()) == (
        403,
        {"error": f"Only {CHILD} may travel here."},
    )

    pulled = client.post(
        "/v1/pull",
        headers=remote.headers(),
        content=PullRequest(roots=(CHILD,)).model_dump_json(),
    )
    withheld = client.post(
        "/v1/pull",
        headers=remote.headers(),
        content=PullRequest(roots=(CHILD, PARENT)).model_dump_json(),
    )

    assert pulled.status_code == 200
    assert withheld.status_code == 403

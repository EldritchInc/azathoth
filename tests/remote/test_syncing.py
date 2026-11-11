"""Tests for pushing to and pulling from a remote, for a local instance (ADR 0124)."""

from pathlib import Path

import httpx
import pytest

from azathoth.remote import (
    AuditEventKind,
    ProtocolMismatchError,
    PullReport,
    PushReport,
    ReceiveRefusedError,
    RemoteClient,
    RemoteDivergedError,
    RemoteRefusedError,
    pull_from,
    push_to,
    restricted_refusal,
)
from azathoth.revisions import Lineage
from azathoth.sensitivity import Sensitivity
from tests.remote.test_client import URL, client_of
from tests.remote.test_closure import (
    BENCHMARK,
    BENCHMARK_ID,
    CHILD,
    PARENT,
    PARENT_ID,
    Instance,
    child,
    parent,
)
from tests.remote.test_pulling import with_benchmark
from tests.remote.test_receiving import CHART, CHART_BYTES, Bare, charts, local_with_history
from tests.remote.test_server import Remote


def pushed(
    local: Instance,
    remote: Remote,
    *roots: Lineage,
) -> PushReport:
    return push_to(
        client_of(remote),
        roots,
        workflows=local.workflows,
        tools=local.tools,
        benchmarks=local.benchmarks,
        content=local.content,
    )


def pulled(
    local: Instance,
    remote: Remote,
    *roots: Lineage,
    include_restricted: bool = False,
) -> PullReport:
    return pull_from(
        client_of(remote),
        roots,
        include_restricted=include_restricted,
        workflows=local.workflows,
        tools=local.tools,
        benchmarks=local.benchmarks,
        content=local.content,
    )


# Pushing


def test_a_push_sends_only_what_the_remote_lacks(
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    theirs.workflows.save(parent())
    remote = Remote(tmp_path, held=theirs)
    local = local_with_history()

    report = pushed(local, remote, PARENT)

    assert report.remote == URL
    assert [(saved.lineage, saved.number) for saved in report.received] == [(PARENT, 2)]
    assert report.already_held == 4
    assert report.content_sent == 0
    assert report.unresolved == local.closure(PARENT).unresolved
    assert [record.revision_digest for record in theirs.workflows.lineage(PARENT_ID)] == [
        record.revision_digest for record in local.workflows.lineage(PARENT_ID)
    ]
    assert remote.audit.kinds() == [AuditEventKind.CAPABILITIES_READ, AuditEventKind.PUSH]


def test_a_push_of_what_the_remote_holds_sends_nothing(
    tmp_path: Path,
) -> None:
    local = local_with_history()
    remote = Remote(tmp_path)

    pushed(local, remote, PARENT)
    again = pushed(local, remote, PARENT)

    assert (again.received, again.already_held, again.content_sent) == ((), 5, 0)
    assert remote.audit.kinds()[-1] is AuditEventKind.CAPABILITIES_READ


def test_a_push_sends_benchmark_content_first(
    tmp_path: Path,
) -> None:
    local = charts(Sensitivity.PUBLIC)
    local.content.put(CHART_BYTES)
    remote = Remote(tmp_path)

    report = pushed(local, remote, BENCHMARK)

    assert report.content_sent == 1
    assert remote.content.get(CHART.digest) == CHART_BYTES
    assert [saved.lineage for saved in report.received] == [BENCHMARK]


def test_content_a_pushed_benchmark_holds_must_be_held_here(
    tmp_path: Path,
) -> None:
    with pytest.raises(ReceiveRefusedError) as caught:
        pushed(charts(None), Remote(tmp_path), BENCHMARK)

    assert str(caught.value) == (
        f"Content {CHART.digest}, which a pushed benchmark holds, is not held here."
    )


def test_restricted_data_is_not_sent_to_a_remote_that_does_not_accept_it(
    tmp_path: Path,
) -> None:
    local = charts(Sensitivity.RESTRICTED)
    local.content.put(CHART_BYTES)
    remote = Remote(tmp_path)

    with pytest.raises(RemoteRefusedError) as caught:
        pushed(local, remote, BENCHMARK)

    assert str(caught.value) == restricted_refusal("This push carries restricted data")
    assert remote.audit.kinds() == [AuditEventKind.CAPABILITIES_READ]
    assert not remote.content.contains(CHART.digest)


def test_restricted_data_is_sent_to_a_remote_that_accepts_it(
    tmp_path: Path,
) -> None:
    local = charts(Sensitivity.RESTRICTED)
    local.content.put(CHART_BYTES)
    remote = Remote(tmp_path, accepts_restricted=True)

    assert pushed(local, remote, BENCHMARK).content_sent == 1
    assert remote.held.benchmarks.lineage(BENCHMARK_ID)


def test_a_diverged_push_is_refused(
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    theirs.workflows.save(parent())
    theirs.workflows.save(parent("Counts differently."))

    with pytest.raises(RemoteDivergedError):
        pushed(local_with_history(), Remote(tmp_path, held=theirs), PARENT)


# Pulling


def test_a_pull_saves_what_is_not_held_and_forks_what_diverged(
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path, held=local_with_history())
    local = Instance()
    local.workflows.save(child())
    local.workflows.save(parent())
    local.workflows.save(parent("Counts my way."))

    report = pulled(local, remote, PARENT)

    assert report.remote == URL
    assert [(saved.lineage, saved.number) for saved in report.received] == [(PARENT, 3)]
    assert report.forked == (PARENT,)
    assert report.withheld == ()
    assert [record.number for record in local.workflows.lineage(PARENT_ID)] == [1, 2, 3]


def test_a_pull_fetches_the_content_it_lacks(
    tmp_path: Path,
) -> None:
    held = with_benchmark(Instance(), Sensitivity.PUBLIC)
    held.content.put(CHART_BYTES)
    remote = Remote(tmp_path, held=held)
    local = Bare()

    report = pulled(local, remote, BENCHMARK)

    assert report.content_fetched == 1
    assert local.content.get(CHART.digest) == CHART_BYTES
    assert pulled(local, remote, BENCHMARK).content_fetched == 0


def test_a_restricted_benchmark_is_withheld_unless_asked_for(
    tmp_path: Path,
) -> None:
    held = with_benchmark(Instance(), Sensitivity.RESTRICTED)
    held.content.put(CHART_BYTES)
    remote = Remote(tmp_path, held=held, accepts_restricted=True)
    local = Bare()

    withheld = pulled(local, remote, BENCHMARK)

    assert (withheld.withheld, withheld.received, withheld.content_fetched) == ((BENCHMARK,), (), 0)

    included = pulled(local, remote, BENCHMARK, include_restricted=True)

    assert [saved.lineage for saved in included.received] == [BENCHMARK]
    assert included.content_fetched == 1


def test_fetched_content_that_is_not_its_digest_is_refused(
    tmp_path: Path,
) -> None:
    held = with_benchmark(Instance(), Sensitivity.PUBLIC)
    held.content.put(CHART_BYTES)
    remote = Remote(tmp_path, held=held)
    real = remote.client

    def tampered(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v1/content/"):
            return httpx.Response(200, content=b"tampered")

        answered = real.request(
            request.method,
            request.url.path,
            content=request.content,
            headers=dict(request.headers),
        )

        return httpx.Response(answered.status_code, content=answered.content)

    client = RemoteClient(
        URL,
        remote.token,
        http=httpx.Client(base_url=URL, transport=httpx.MockTransport(tampered)),
    )
    local = Bare()

    with pytest.raises(ReceiveRefusedError) as caught:
        pull_from(
            client,
            (BENCHMARK,),
            include_restricted=False,
            workflows=local.workflows,
            tools=local.tools,
            benchmarks=local.benchmarks,
            content=local.content,
        )

    assert str(caught.value).startswith(f"Content sent as {CHART.digest} is ")
    assert local.benchmarks.lineage(BENCHMARK_ID) == ()


# Protocols


@pytest.mark.parametrize("pulling", [False, True], ids=["push", "pull"])
def test_a_remote_of_another_protocol_is_sent_nothing(
    pulling: bool,
) -> None:
    asked: list[str] = []

    def other_protocol(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)

        return httpx.Response(
            200,
            json={"protocol": 2, "azathoth_version": "2.0.0", "schema_version": 9},
        )

    client = RemoteClient(
        URL,
        "azr_token",
        http=httpx.Client(base_url=URL, transport=httpx.MockTransport(other_protocol)),
    )
    local = local_with_history()

    with pytest.raises(ProtocolMismatchError):
        if pulling:
            pull_from(
                client,
                (CHILD,),
                include_restricted=False,
                workflows=local.workflows,
                tools=local.tools,
                benchmarks=local.benchmarks,
                content=local.content,
            )
        else:
            push_to(
                client,
                (CHILD,),
                workflows=local.workflows,
                tools=local.tools,
                benchmarks=local.benchmarks,
                content=local.content,
            )

    assert asked == ["/v1/capabilities"]

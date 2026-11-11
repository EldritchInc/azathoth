"""Tests for pushing to and pulling from a remote through the service API (ADR 0124)."""

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from azathoth import api
from azathoth.api.remote import NO_TOKEN_MESSAGE, lineages
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import REMOTE_TOKEN_VARIABLE, HttpClient
from azathoth.revisions import Lineage, RevisionKind
from azathoth.sensitivity import Sensitivity
from tests.remote.test_closure import (
    CHILD_ID,
    COUNT_ID,
    PARENT,
    PARENT_ID,
    Instance,
    child,
    parent,
)
from tests.remote.test_receiving import CHART_BYTES, charts, local_with_history
from tests.remote.test_server import Remote

URL = "http://remote.test"


@pytest.fixture
def instance(
    tmp_path: Path,
) -> Iterator[api.Azathoth]:
    """Open a local SQLite instance holding the child workflow, its parent and their tools."""

    database = tmp_path / "local.db"
    held = open_repositories(database)
    source = local_with_history()

    for record in source.closure(PARENT).revisions:
        if record.lineage.kind is RevisionKind.TOOL:
            assert record.lineage.version is not None
            revision = source.tools.document_revision(record.lineage.id, record.lineage.version, 1)
            assert revision is not None
            held.tools.save_document(revision.document)

    held.workflows.save(child())
    held.workflows.save(parent())
    held.workflows.save(parent("Counts again."))

    with api.open(database) as opened:
        yield opened


def served(
    remote: Remote,
) -> HttpClient:
    return remote.client


# Naming a remote


def test_a_remote_is_reached_with_the_token_given_or_its_variable(
    instance: api.Azathoth,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = Remote(tmp_path)

    assert instance.remote(URL, token=remote.token, http=lambda: served(remote)).url == URL

    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, remote.token)
    named = instance.remote(f"{URL}/", http=lambda: served(remote))

    assert named.url == URL
    assert named.capabilities().protocol == 1


@pytest.mark.parametrize("token", [None, ""], ids=["unset", "empty"])
def test_a_remote_without_a_token_is_refused(
    instance: api.Azathoth,
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
) -> None:
    monkeypatch.delenv(REMOTE_TOKEN_VARIABLE, raising=False)

    if token is not None:
        monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, token)

    with pytest.raises(api.InvalidArgumentError) as caught:
        instance.remote(URL)

    assert str(caught.value) == NO_TOKEN_MESSAGE
    assert NO_TOKEN_MESSAGE == (
        "No remote token was given; set AZATHOTH_REMOTE_TOKEN to one created on the remote "
        "with `azathoth remote token create`."
    )


def test_a_remote_url_that_is_not_one_is_refused(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidArgumentError) as caught:
        instance.remote("azathoth.example.com", token="azr_token")

    assert str(caught.value) == "Remote URL 'azathoth.example.com' is not an http or https URL."


def test_documents_are_named_by_kind() -> None:
    assert lineages(
        workflows=(PARENT_ID,),
        tools=((COUNT_ID, "1.0.0"),),
        benchmarks=(CHILD_ID,),
    ) == (
        PARENT,
        Lineage(kind=RevisionKind.TOOL, id=COUNT_ID, version="1.0.0"),
        Lineage(kind=RevisionKind.BENCHMARK, id=CHILD_ID),
    )

    with pytest.raises(api.InvalidArgumentError) as caught:
        lineages(workflows=(), tools=(), benchmarks=())

    assert str(caught.value) == "Name a workflow, tool version or benchmark to send."


# Pushing and pulling


def test_a_push_and_a_pull_travel_through_the_api(
    instance: api.Azathoth,
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path)
    reached = instance.remote(URL, token=remote.token, http=lambda: served(remote))

    report = reached.push(workflows=[PARENT_ID])

    assert isinstance(report, api.PushReport)
    assert [saved.lineage for saved in report.received][-2:] == [PARENT, PARENT]
    assert remote.held.workflows.get(PARENT_ID) == parent("Counts again.")

    remote.held.workflows.save(parent("Counts at the remote."))
    pulled = reached.pull(workflows=[PARENT_ID])

    assert isinstance(pulled, api.PullReport)
    assert [(saved.lineage, saved.number) for saved in pulled.received] == [(PARENT, 3)]
    assert pulled.forked == ()
    assert instance.workflows.get(PARENT_ID).revision.number == 3


def test_a_diverged_push_is_a_conflict(
    instance: api.Azathoth,
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    theirs.workflows.save(parent("Counts differently."))
    remote = Remote(tmp_path, held=theirs)

    with pytest.raises(api.RemoteRefusedError) as refused:
        instance.remote(URL, token=remote.token, http=lambda: served(remote)).push(
            workflows=[PARENT_ID]
        )

    assert refused.value.code == "remote_refused"

    theirs = Instance()
    theirs.workflows.save(child())
    theirs.workflows.save(parent())
    theirs.workflows.save(parent("Counts differently."))
    (tmp_path / "diverged").mkdir()
    diverged = Remote(tmp_path / "diverged", held=theirs)

    with pytest.raises(api.RemoteDivergedError) as caught:
        instance.remote(URL, token=diverged.token, http=lambda: served(diverged)).push(
            workflows=[PARENT_ID]
        )

    assert isinstance(caught.value, api.ConflictError)
    assert caught.value.code == "remote_diverged"


def test_restricted_data_is_refused_before_it_is_sent(
    tmp_path: Path,
) -> None:
    database = tmp_path / "local.db"
    held = open_repositories(database)
    source = charts(Sensitivity.RESTRICTED)
    (dataset,) = source.benchmarks.datasets()
    held.benchmarks.save(dataset)
    held.content.put(CHART_BYTES)
    remote = Remote(tmp_path)

    with api.open(database) as instance, pytest.raises(api.RemoteRefusedError) as caught:
        instance.remote(URL, token=remote.token, http=lambda: served(remote)).push(
            benchmarks=[dataset.id]
        )

    assert str(caught.value).startswith("This push carries restricted data, and this remote")


def test_a_remote_of_another_protocol_is_a_protocol_error(
    instance: api.Azathoth,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"protocol": 2, "azathoth_version": "2.0.0", "schema_version": 9},
        )
    )

    with pytest.raises(api.RemoteProtocolError) as caught:
        instance.remote(
            URL,
            token="azr_token",
            http=lambda: httpx.Client(base_url=URL, transport=transport),
        ).pull(workflows=[PARENT_ID])

    assert caught.value.code == "remote_protocol"
    assert str(caught.value).startswith("The remote speaks remote protocol 2,")


def test_a_remote_not_reached_is_unreachable(
    instance: api.Azathoth,
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(api.RemoteUnreachableError) as caught:
        instance.remote(
            URL,
            token="azr_token",
            http=lambda: httpx.Client(base_url=URL, transport=httpx.MockTransport(refuse)),
        ).capabilities()

    assert caught.value.code == "remote_unreachable"
    assert str(caught.value) == f"The remote at {URL} could not be reached: Connection refused"


def test_a_closed_instance_reaches_no_remote(
    instance: api.Azathoth,
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path)
    reached = instance.remote(URL, token=remote.token, http=lambda: served(remote))
    instance.close()

    with pytest.raises(api.InstanceClosedError):
        reached.push(workflows=[PARENT_ID])

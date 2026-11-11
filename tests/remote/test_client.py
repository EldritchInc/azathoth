"""Tests for the HTTP client a local instance reaches a remote with (ADR 0124)."""

from pathlib import Path

import httpx
import pytest

from azathoth.remote import (
    DEFAULT_TIMEOUT_SECONDS,
    REMOTE_TOKEN_VARIABLE,
    Capabilities,
    MissingRequest,
    PullRequest,
    PushBundle,
    RemoteClient,
    RemoteDivergedError,
    RemoteNotFoundError,
    RemoteRefusedError,
    RemoteUnreachableError,
    require_remote_url,
)
from azathoth.sensitivity import Sensitivity
from tests.remote.test_closure import CHILD, PARENT, PARENT_ID, Instance, child, parent
from tests.remote.test_receiving import CHART, CHART_BYTES, bundle, local_with_history
from tests.remote.test_server import Remote

URL = "http://remote.test"


def client_of(
    remote: Remote,
    token: str | None = None,
) -> RemoteClient:
    return RemoteClient(URL, remote.token if token is None else token, http=remote.client)


def answering(
    status: int,
    body: bytes,
) -> RemoteClient:
    """Return a client of a server that answers everything with one response."""

    transport = httpx.MockTransport(lambda request: httpx.Response(status, content=body))

    return RemoteClient(URL, "azr_token", http=httpx.Client(base_url=URL, transport=transport))


# URLs and tokens


@pytest.mark.parametrize(
    ("url", "kept"),
    [
        ("https://azathoth.example.com/", "https://azathoth.example.com"),
        ("http://127.0.0.1:8470", "http://127.0.0.1:8470"),
        ("https://example.com/azathoth/", "https://example.com/azathoth"),
    ],
)
def test_a_remote_url_is_http_or_https(
    url: str,
    kept: str,
) -> None:
    assert require_remote_url(url) == kept


@pytest.mark.parametrize("url", ["azathoth.example.com", "ftp://example.com", "https://", ""])
def test_any_other_url_is_refused(
    url: str,
) -> None:
    with pytest.raises(ValueError) as caught:
        require_remote_url(url)

    assert str(caught.value) == f"Remote URL {url!r} is not an http or https URL."


def test_the_token_is_read_from_its_variable_and_requests_wait_a_minute() -> None:
    assert REMOTE_TOKEN_VARIABLE == "AZATHOTH_REMOTE_TOKEN"
    assert DEFAULT_TIMEOUT_SECONDS == 60.0


def test_a_client_closes_only_the_http_client_it_opened(
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path)

    with client_of(remote) as client:
        assert client.capabilities().protocol == 1

    assert not remote.client.is_closed

    owned = RemoteClient(URL, "azr_token")
    owned.close()
    opened = owned._http

    assert isinstance(opened, httpx.Client)
    assert opened.is_closed


# Speaking the protocol


def test_each_route_is_spoken(
    tmp_path: Path,
) -> None:
    held = Instance()
    held.workflows.save(child())
    remote = Remote(tmp_path, held=held)
    client = client_of(remote)
    sent = bundle(local_with_history(), PARENT)

    assert isinstance(client.capabilities(), Capabilities)
    assert client.missing(
        MissingRequest(
            lineages=(CHILD,),
            revisions=tuple(record.revision_digest for record in sent.revisions),
        )
    ).revisions == tuple(
        record.revision_digest for record in sent.revisions if record.lineage != CHILD
    )

    client.put_content(CHART.digest, CHART_BYTES, sensitivity=Sensitivity.PUBLIC)

    assert client.get_content(CHART.digest) == CHART_BYTES
    assert [saved.lineage for saved in client.push(sent).received] == [PARENT, PARENT]
    assert client.pull(PullRequest(roots=(PARENT,))).bundle.revisions == sent.revisions


# Refusals


def test_a_refusal_carries_the_remotes_message_and_status(
    tmp_path: Path,
) -> None:
    remote = Remote(tmp_path)

    with pytest.raises(RemoteRefusedError) as caught:
        client_of(remote, token="azr_unknown").capabilities()

    assert caught.value.status == 401
    assert str(caught.value).startswith("This remote does not know the token given.")


def test_a_diverged_push_is_its_own_refusal(
    tmp_path: Path,
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    theirs.workflows.save(parent())
    theirs.workflows.save(parent("Counts differently."))

    with pytest.raises(RemoteDivergedError) as caught:
        client_of(Remote(tmp_path, held=theirs)).push(bundle(local_with_history(), PARENT))

    assert caught.value.status == 409
    assert str(caught.value).startswith(f"Workflow {PARENT_ID} has diverged")


def test_content_not_held_is_not_found(
    tmp_path: Path,
) -> None:
    with pytest.raises(RemoteNotFoundError) as caught:
        client_of(Remote(tmp_path)).get_content("f" * 64)

    assert (caught.value.status, str(caught.value)) == (
        404,
        f"This remote holds no content {'f' * 64}.",
    )


def test_a_push_the_checks_refuse_is_refused(
    tmp_path: Path,
) -> None:
    with pytest.raises(RemoteRefusedError) as caught:
        client_of(Remote(tmp_path)).push(PushBundle(protocol=2))

    assert type(caught.value) is RemoteRefusedError
    assert caught.value.status == 400


@pytest.mark.parametrize(
    "body",
    [b"<html>Bad gateway</html>", b'{"detail": "nope"}', b'["error"]'],
    ids=["html", "other-json", "list"],
)
def test_an_answer_that_is_no_remotes_refusal_says_so(
    body: bytes,
) -> None:
    with pytest.raises(RemoteUnreachableError) as caught:
        answering(502, body).capabilities()

    assert caught.value.status == 502
    assert str(caught.value) == (
        f"The remote at {URL} answered 502 without saying why; it may not be an Azathoth remote."
    )


def test_an_answer_that_is_not_the_protocols_says_so() -> None:
    with pytest.raises(RemoteUnreachableError) as caught:
        answering(200, b'{"status": "ok"}').capabilities()

    assert str(caught.value) == (
        f"The remote at {URL} answered with something other than a Capabilities; it may not be "
        "an Azathoth remote, or not of this protocol."
    )


def test_a_remote_not_reached_says_so() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    client = RemoteClient(
        URL,
        "azr_token",
        http=httpx.Client(base_url=URL, transport=httpx.MockTransport(refuse)),
    )

    with pytest.raises(RemoteUnreachableError) as caught:
        client.capabilities()

    assert caught.value.status is None
    assert str(caught.value) == f"The remote at {URL} could not be reached: Connection refused"


def test_the_token_is_sent_as_a_bearer_token() -> None:
    seen: list[str | None] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, content=b"x")

    client = RemoteClient(
        URL,
        "azr_token",
        http=httpx.Client(base_url=URL, transport=httpx.MockTransport(record)),
    )

    assert client.get_content("f" * 64) == b"x"
    assert seen == ["Bearer azr_token"]


def test_content_is_sent_with_its_label(
    tmp_path: Path,
) -> None:
    with pytest.raises(RemoteRefusedError) as caught:
        client_of(Remote(tmp_path)).put_content(
            CHART.digest,
            CHART_BYTES,
            sensitivity=Sensitivity.RESTRICTED,
        )

    assert caught.value.status == 403

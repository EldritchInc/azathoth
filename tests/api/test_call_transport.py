"""Tests of sending calls of the service API to a remote over HTTP (ADR 0137)."""

import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from azathoth.api.connected import CallTransport
from azathoth.api.errors import (
    NotFoundError,
    PermissionDeniedError,
    RemoteRefusedError,
    RemoteUnavailableError,
    RemoteUnreachableError,
)
from azathoth.api.models import InstanceDescription
from azathoth.remote.calling import CallArgumentsError, NotServedError
from tests.remote.asgi import AsgiHttp
from tests.remote.test_call_audit import Broken
from tests.remote.test_call_routes import ERIS, Served
from tests.remote.test_service_routes import GUEST

URL = "http://remote.test"

TOKEN = "azr_test"

MISSING = UUID("c1110000-0000-4000-8000-000000000001")


class Fixed:
    """An HTTP client of a server that answers everything with one response."""

    def __init__(
        self,
        status: int,
        body: bytes,
    ) -> None:
        self.status_code = status
        self.content = body
        self.closed = False

    @property
    def is_success(
        self,
    ) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> object:
        return json.loads(self.content)

    def request(
        self,
        method: str,
        url: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> "Fixed":
        return self

    def close(
        self,
    ) -> None:
        self.closed = True


class Unreached(Fixed):
    """An HTTP client that reaches no server."""

    def __init__(self) -> None:
        super().__init__(0, b"")

    def request(
        self,
        method: str,
        url: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> "Fixed":
        raise httpx.ConnectError("Connection refused")


def transport(
    served: Served,
) -> tuple[CallTransport, AsgiHttp]:
    """Return a transport to a served remote, and the client it sends over."""

    http = AsgiHttp(served.app)

    return CallTransport(URL, TOKEN, http=http), http


@pytest.fixture
def served(
    tmp_path: Path,
) -> Served:
    return Served(tmp_path / "azathoth.db", principal=ERIS)


# Calls and their results


def test_a_result_is_read_as_the_call_returns_it(
    served: Served,
) -> None:
    sent, _ = transport(served)
    described = sent.call("describe", {})

    assert isinstance(described, InstanceDescription)
    assert described.backend == "sqlite"
    assert sent.call("workflows.list", {}) == ()


def test_a_call_is_posted_to_its_route_with_the_token_and_only_the_arguments_given(
    served: Served,
) -> None:
    sent, http = transport(served)

    with pytest.raises(NotFoundError):
        sent.call("runs.list", {"workflow_id": MISSING})

    ((method, url, body),) = http.sent

    assert (method, url) == ("POST", "/v1/calls/runs.list")
    assert json.loads(body) == {"workflow_id": str(MISSING)}
    assert served.policy.asked[0][0] == "Eris"


def test_what_a_caller_makes_through_a_remote_is_theirs(
    served: Served,
) -> None:
    sent, _ = transport(served)
    created = sent.call("benchmarks.create", {"name": "charts", "description": "Charts."})

    assert created.benchmark.revision.author.name == "Eris"
    assert [summary.id for summary in sent.call("benchmarks.list", {})] == [created.benchmark.id]


# What is refused before anything is sent


def test_arguments_that_are_not_the_calls_are_refused_before_anything_is_sent(
    served: Served,
) -> None:
    sent, http = transport(served)

    with pytest.raises(CallArgumentsError, match="at flavour: Extra inputs are not permitted"):
        sent.call("workflows.list", {"flavour": "dry"})

    assert http.sent == []


def test_a_job_is_not_sent(
    served: Served,
) -> None:
    sent, http = transport(served)

    with pytest.raises(NotServedError, match=r"^A remote runs runs\.run as a job"):
        sent.call("runs.run", {})

    assert http.sent == []


# What the remote refuses


def test_an_api_error_comes_back_as_its_own_kind_with_the_remotes_message(
    served: Served,
) -> None:
    sent, _ = transport(served)

    with pytest.raises(NotFoundError) as caught:
        sent.call("workflows.get", {"workflow_id": MISSING})

    assert type(caught.value) is NotFoundError
    assert str(caught.value) == f"Workflow {MISSING} is not configured."


def test_a_caller_the_policy_refuses_is_told_why(
    tmp_path: Path,
) -> None:
    sent, _ = transport(Served(tmp_path / "azathoth.db", principal=GUEST))

    with pytest.raises(PermissionDeniedError) as caught:
        sent.call("benchmarks.create", {"name": "charts", "description": "Charts."})

    assert str(caught.value) == "guest may not edit benchmark on this remote: only its owner may."


def test_a_token_the_remote_does_not_know_is_its_refusal_with_status_and_code(
    tmp_path: Path,
) -> None:
    sent, _ = transport(Served(tmp_path / "azathoth.db", principal=None))

    with pytest.raises(RemoteRefusedError) as caught:
        sent.call("describe", {})

    assert type(caught.value) is RemoteRefusedError
    assert (caught.value.status, caught.value.refusal) == (401, "unauthenticated")
    assert str(caught.value).startswith("This remote does not know the token given.")


def test_a_remote_whose_audit_is_down_may_answer_later(
    tmp_path: Path,
) -> None:
    sent, _ = transport(Served(tmp_path / "azathoth.db", principal=ERIS, audit=Broken()))

    with pytest.raises(RemoteUnavailableError) as caught:
        sent.call("benchmarks.create", {"name": "charts", "description": "Charts."})

    assert (caught.value.status, caught.value.refusal) == (503, "audit_unavailable")


def test_a_remote_serving_only_the_protocol_says_so(
    tmp_path: Path,
) -> None:
    sent, _ = transport(Served(tmp_path / "azathoth.db", serves_calls=False))

    with pytest.raises(
        NotFoundError,
        match=r"^This remote serves only push, pull and status, not the service API\.$",
    ):
        sent.call("describe", {})


# A server that is no remote serving the service API


def test_a_remote_not_reached_is_unreachable() -> None:
    sent = CallTransport(URL, TOKEN, http=Unreached())

    with pytest.raises(
        RemoteUnreachableError,
        match=r"^The remote at http://remote\.test could not be reached: Connection refused$",
    ):
        sent.call("describe", {})


def test_a_server_without_the_route_may_not_serve_the_service_api() -> None:
    sent = CallTransport(URL, TOKEN, http=Fixed(404, b"Not Found"))

    with pytest.raises(RemoteUnreachableError) as caught:
        sent.call("describe", {})

    assert str(caught.value) == (
        "The remote at http://remote.test does not serve describe; it may not serve the service "
        "API, which a remote does from Azathoth 1.6."
    )


@pytest.mark.parametrize(
    "body",
    [b"<html>Bad gateway</html>", b'{"error": "No code."}', b'{"status": "ok"}'],
    ids=["html", "no-code", "no-error"],
)
def test_a_refusal_that_says_nothing_is_not_a_remotes(
    body: bytes,
) -> None:
    sent = CallTransport(URL, TOKEN, http=Fixed(502, body))

    with pytest.raises(RemoteUnreachableError) as caught:
        sent.call("workflows.list", {})

    assert str(caught.value) == (
        "The remote at http://remote.test answered workflows.list with 502 without saying why; "
        "it may not be an Azathoth remote."
    )


def test_a_result_that_is_not_the_calls_is_not_a_remotes() -> None:
    sent = CallTransport(URL, TOKEN, http=Fixed(200, b'{"workflows": "all of them"}'))

    with pytest.raises(RemoteUnreachableError) as caught:
        sent.call("workflows.list", {})

    assert str(caught.value) == (
        "The remote at http://remote.test answered workflows.list with something other than its "
        "result; it may serve another version of the service API."
    )


# The transport itself


def test_a_url_that_is_not_http_or_https_is_refused() -> None:
    with pytest.raises(ValueError, match="is not an http or https URL"):
        CallTransport("ftp://remote.test", TOKEN, http=Fixed(200, b"{}"))


def test_a_transport_closes_only_a_client_it_opened() -> None:
    given = Fixed(200, b"[]")

    with CallTransport(URL + "/", TOKEN, http=given) as sent:
        assert sent.url == URL

    assert not given.closed

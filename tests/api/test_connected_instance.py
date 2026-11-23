"""Tests of an instance connected to a remote, called as a local instance is (ADR 0137)."""

import inspect
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from azathoth import api
from azathoth.api.calls import SERVICE_CALLS
from azathoth.api.connected import (
    JOB_REFUSAL,
    NOT_IMPLEMENTED,
    CallTransport,
    ConnectedInstance,
    Instance,
)
from azathoth.api.errors import (
    CLOSED_MESSAGE,
    InstanceClosedError,
    InvalidArgumentError,
    NotFoundError,
    RemoteRefusedError,
)
from azathoth.api.instance import Azathoth
from azathoth.api.remote import no_token_message
from azathoth.remote.server import JOB_CODE
from tests.api.test_calls import functions
from tests.remote.asgi import AsgiHttp
from tests.remote.test_call_routes import ERIS, Served

URL = "http://remote.test"

MISSING = UUID("c1120000-0000-4000-8000-000000000001")

NEVER_ON_AN_INSTANCE = {"remote", "remotes"}
"""What a local instance has that names its own remotes, which no remote serves."""


class Connected:
    """An instance connected to a served remote, and the HTTP client it sends over."""

    def __init__(
        self,
        served: Served,
    ) -> None:
        self.served = served
        self.http = AsgiHttp(served.app)
        self.instance = api.connect(URL, token="azr_test", http=self.http)


@pytest.fixture
def connected(
    tmp_path: Path,
) -> Iterator[Connected]:
    made = Connected(Served(tmp_path / "azathoth.db", principal=ERIS))

    with made.instance:
        yield made


def public(
    kind: type,
) -> set[str]:
    """Return the names a class shows its callers: every member but private ones."""

    return {name for name in dir(kind) if not name.startswith("_")}


def protocol_members() -> set[str]:
    """Return what `Instance` declares, but what every class has."""

    return {name for name in vars(Instance) if not name.startswith("_")} | {
        "__enter__",
        "__exit__",
    }


# Its shape


def test_an_instance_is_everything_a_local_one_is_but_its_own_remotes() -> None:
    assert protocol_members() - {"__enter__", "__exit__"} == public(Azathoth) - NEVER_ON_AN_INSTANCE


def test_a_connected_instance_has_everything_an_instance_does() -> None:
    assert protocol_members() <= public(ConnectedInstance) | {"__enter__", "__exit__"}


def test_a_local_and_a_connected_instance_are_both_instances(
    tmp_path: Path,
) -> None:
    connected: Instance = Connected(Served(tmp_path / "azathoth.db")).instance
    local: Instance

    with api.open(tmp_path / "azathoth.db") as local:
        assert isinstance(local, Azathoth)

    assert isinstance(connected, ConnectedInstance)


@pytest.mark.parametrize(
    "name",
    [call.name for call in SERVICE_CALLS if call.served],
)
def test_every_served_call_is_on_a_connected_instance_as_the_local_call_takes_it(
    connected: Connected,
    name: str,
) -> None:
    collection, _, method = name.rpartition(".")
    owner = getattr(connected.instance, collection) if collection else connected.instance
    local = inspect.signature(functions()[name])

    assert inspect.signature(getattr(owner, method)) == local.replace(
        parameters=list(local.parameters.values())[1:]
    )

    if collection:
        assert getattr(owner, method).__doc__ == functions()[name].__doc__


def test_a_name_that_is_no_call_is_no_attribute(
    connected: Connected,
) -> None:
    workflows: Any = connected.instance.workflows

    with pytest.raises(AttributeError, match="The service API's workflows have no call named fly"):
        _ = workflows.fly

    with pytest.raises(AttributeError):
        _ = workflows._author

    assert not hasattr(connected.instance, "remotes")
    assert not hasattr(connected.instance, "remote")


# Calling


def test_arguments_are_bound_as_the_local_call_binds_them_and_only_those_given_sent(
    connected: Connected,
) -> None:
    with pytest.raises(NotFoundError, match=str(MISSING)):
        connected.instance.workflows.history(MISSING)

    with pytest.raises(NotFoundError, match=str(MISSING)):
        connected.instance.runs.list(workflow_id=MISSING, limit=5)

    (first, second) = [json.loads(body) for _, _, body in connected.http.sent]

    assert first == {"workflow_id": str(MISSING)}
    assert second == {"workflow_id": str(MISSING), "limit": 5}


def test_arguments_python_would_refuse_locally_are_refused_before_anything_is_sent(
    connected: Connected,
) -> None:
    get: Any = connected.instance.workflows.get

    with pytest.raises(TypeError):
        get()

    with pytest.raises(TypeError):
        get(MISSING, MISSING, MISSING)

    assert connected.http.sent == []


def test_a_result_is_what_the_local_call_returns(
    connected: Connected,
) -> None:
    created = connected.instance.benchmarks.create("charts", "Charts.")
    listed = connected.instance.benchmarks.list()

    assert isinstance(created, api.BenchmarkImport)
    assert [summary.id for summary in listed] == [created.benchmark.id]
    assert connected.instance.describe().backend == "sqlite"


@pytest.mark.parametrize(
    "name",
    [call.name for call in SERVICE_CALLS if call.job],
)
def test_a_job_is_refused_as_a_remote_refuses_one_and_nothing_is_sent(
    connected: Connected,
    name: str,
) -> None:
    collection, _, method = name.rpartition(".")

    with pytest.raises(RemoteRefusedError) as caught:
        getattr(getattr(connected.instance, collection), method)()

    assert (caught.value.status, caught.value.refusal) == (NOT_IMPLEMENTED, JOB_REFUSAL)
    assert str(caught.value) == (
        f"{name} runs on a remote's workers, which a connected instance does not call yet."
    )
    assert connected.http.sent == []


def test_a_job_is_refused_with_the_code_a_remote_refuses_one_with() -> None:
    assert JOB_REFUSAL == JOB_CODE


# Closing


def test_a_closed_instance_sends_nothing() -> None:
    http = AsgiHttp(None)
    instance = api.connect(URL, token="azr_test", http=http)
    instance.close()
    instance.close()

    with pytest.raises(InstanceClosedError, match=f"^{CLOSED_MESSAGE}$"):
        instance.workflows.list()

    with pytest.raises(InstanceClosedError):
        instance.describe()

    assert instance.closed
    assert http.sent == []


def test_closing_leaves_a_client_it_was_given_open() -> None:
    http = AsgiHttp(None)

    with api.connect(URL, token="azr_test", http=http) as instance:
        opened = not instance.closed

    assert opened
    assert instance.closed
    assert not http.closed


# Connecting


def test_a_connection_reads_its_token_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AZATHOTH_REMOTE_TOKEN", "azr_test")
    served = Served(tmp_path / "azathoth.db", principal=ERIS)
    http = AsgiHttp(served.app)

    with api.connect(URL + "/", http=http) as instance:
        assert instance.url == URL
        assert instance.workflows.list() == ()


def test_a_connection_without_a_token_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZATHOTH_REMOTE_TOKEN", raising=False)

    with pytest.raises(InvalidArgumentError) as caught:
        api.connect(URL)

    assert str(caught.value) == no_token_message("AZATHOTH_REMOTE_TOKEN")


def test_a_connection_to_what_is_no_http_url_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match="is not an http or https URL"):
        api.connect("ftp://remote.test", token="azr_test")


def test_a_transport_can_be_called_on_its_own(
    connected: Connected,
) -> None:
    transport = CallTransport(URL, "azr_test", http=connected.http)

    assert ConnectedInstance(transport).workflows.list() == ()

"""Tests of connecting to the service API of a remote this instance named (ADR 0137)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from azathoth import api
from azathoth.api.connected import ConnectedInstance, Instance
from azathoth.api.remote import no_token_message
from azathoth.remote import REMOTE_TOKEN_VARIABLE
from tests.remote.asgi import AsgiHttp
from tests.remote.test_call_routes import ERIS, Served

URL = "http://staging.test"

VARIABLE = "STAGING_TOKEN"


@pytest.fixture
def local(
    tmp_path: Path,
) -> Iterator[api.Azathoth]:
    """Open a local instance that names the remote at `URL` staging, its token in `VARIABLE`."""

    database = tmp_path / "local.db"
    sqlite3.connect(database).close()

    with api.open(database) as opened:
        opened.remotes.add("staging", URL, token_variable=VARIABLE)
        yield opened


@pytest.fixture
def http(
    tmp_path: Path,
) -> AsgiHttp:
    return AsgiHttp(Served(tmp_path / "remote.db", principal=ERIS).app)


def test_a_named_remote_is_connected_to_with_the_token_its_variable_holds(
    local: api.Azathoth,
    http: AsgiHttp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(VARIABLE, "azr_staging")
    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, "azr_default")

    with local.remote("staging", http=lambda: http).connect() as remote:
        connected: Instance = remote

        assert connected.workflows.list() == ()
        assert remote.url == URL

    assert http.authorizations == ["Bearer azr_staging"]


def test_a_remote_named_by_url_is_connected_to_with_the_token_given(
    local: api.Azathoth,
    http: AsgiHttp,
) -> None:
    with local.remote(f"{URL}/", token="azr_given", http=lambda: http).connect() as remote:
        assert remote.describe().backend == "sqlite"

    assert http.authorizations == ["Bearer azr_given"]


def test_a_named_remote_whose_variable_is_unset_is_refused_naming_it(
    local: api.Azathoth,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(VARIABLE, raising=False)

    with pytest.raises(api.InvalidArgumentError) as caught:
        local.remote("staging").connect()

    assert str(caught.value) == no_token_message(VARIABLE)


def test_a_connection_outlives_the_instance_that_named_it(
    local: api.Azathoth,
    http: AsgiHttp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(VARIABLE, "azr_staging")
    remote = local.remote("staging", http=lambda: http).connect()
    local.close()

    with remote:
        assert isinstance(remote, ConnectedInstance)
        assert remote.benchmarks.list() == ()


def test_each_connection_is_its_own(
    local: api.Azathoth,
    http: AsgiHttp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(VARIABLE, "azr_staging")
    named = local.remote("staging", http=lambda: http)
    first = named.connect()
    second = named.connect()
    first.close()

    assert first is not second
    assert not second.closed
    assert second.workflows.list() == ()

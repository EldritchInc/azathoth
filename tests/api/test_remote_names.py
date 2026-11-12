"""Tests for the remotes an instance names, through the service API (ADR 0126)."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from azathoth import api
from azathoth.api.remote import is_remote_url, no_token_message, not_named_message
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import REMOTE_TOKEN_VARIABLE, PortfolioResponse
from tests.remote.test_server import Remote

URL = "http://remote.test"

STAGING = "https://staging.example.com"

SHARED_TOKEN = "AZATHOTH_SHARED_TOKEN"


@pytest.fixture
def database(
    tmp_path: Path,
) -> Path:
    """Return an initialized local SQLite instance's file."""

    path = tmp_path / "local.db"
    open_repositories(path).remotes.remotes()

    return path


@pytest.fixture
def instance(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[api.Azathoth]:
    """Open the local instance, with no token variable set."""

    monkeypatch.delenv(REMOTE_TOKEN_VARIABLE, raising=False)
    monkeypatch.delenv(SHARED_TOKEN, raising=False)

    with api.open(database) as opened:
        yield opened


# Naming remotes


def test_a_remote_is_named_listed_and_got(
    instance: api.Azathoth,
) -> None:
    origin = instance.remotes.add("origin", f"{URL}/")
    staging = instance.remotes.add("staging", STAGING, token_variable=SHARED_TOKEN)

    assert (origin.name, origin.url, origin.token_variable) == (
        "origin",
        URL,
        REMOTE_TOKEN_VARIABLE,
    )
    assert staging.token_variable == SHARED_TOKEN
    assert instance.remotes.list() == (origin, staging)
    assert instance.remotes.get("staging") == staging
    assert isinstance(origin, api.NamedRemote)


def test_names_are_kept_in_the_instances_database(
    database: Path,
) -> None:
    with api.open(database) as first:
        added = first.remotes.add("origin", URL)

    with api.open(database) as second:
        assert second.remotes.list() == (added,)


def test_a_name_already_given_is_a_conflict(
    instance: api.Azathoth,
) -> None:
    instance.remotes.add("origin", URL)

    with pytest.raises(api.ConflictError) as caught:
        instance.remotes.add("origin", STAGING)

    assert str(caught.value) == (
        f"Remote origin is already named, for {URL}; remove it first, or choose another name."
    )


@pytest.mark.parametrize(
    ("name", "url", "variable", "message"),
    [
        (
            "my remote",
            URL,
            REMOTE_TOKEN_VARIABLE,
            "Remote name 'my remote' is not one: use 1 to 64 letters, digits, '_' or '-'.",
        ),
        (
            "origin",
            "remote.test",
            REMOTE_TOKEN_VARIABLE,
            "Remote URL 'remote.test' is not an http or https URL.",
        ),
        (
            "origin",
            URL,
            "SHARED-TOKEN",
            "Token variable 'SHARED-TOKEN' is not an environment variable's name: use letters, "
            "digits and '_', not beginning with a digit.",
        ),
    ],
    ids=["name", "url", "variable"],
)
def test_a_name_url_or_variable_that_is_not_one_is_an_invalid_argument(
    instance: api.Azathoth,
    name: str,
    url: str,
    variable: str,
    message: str,
) -> None:
    with pytest.raises(api.InvalidArgumentError) as caught:
        instance.remotes.add(name, url, token_variable=variable)

    assert str(caught.value) == message
    assert instance.remotes.list() == ()


def test_a_name_never_given_is_not_found(
    instance: api.Azathoth,
) -> None:
    for call in (instance.remotes.get, instance.remotes.remove, instance.remote):
        with pytest.raises(api.NotFoundError) as caught:
            call("origin")

        assert str(caught.value) == (
            "No remote is named 'origin'; name one with `azathoth remote add <NAME> <URL>`."
        )

    assert not_named_message("origin") == str(caught.value)


def test_removing_a_name_forgets_it_and_its_portfolio_snapshot(
    instance: api.Azathoth,
    database: Path,
) -> None:
    snapshots = open_repositories(database).remote_portfolio_snapshots
    origin = instance.remotes.add("origin", URL)
    staging = instance.remotes.add("staging", STAGING)
    snapshots.save(URL, PortfolioResponse())
    snapshots.save(STAGING, PortfolioResponse())

    assert instance.remotes.remove("origin") == origin
    assert instance.remotes.list() == (staging,)
    assert snapshots.get(URL) is None
    assert snapshots.get(STAGING) is not None


def test_a_snapshot_another_name_shares_is_kept(
    instance: api.Azathoth,
    database: Path,
) -> None:
    snapshots = open_repositories(database).remote_portfolio_snapshots
    instance.remotes.add("origin", URL)
    instance.remotes.add("same", URL)
    snapshots.save(URL, PortfolioResponse())

    instance.remotes.remove("origin")

    assert snapshots.get(URL) is not None

    instance.remotes.remove("same")

    assert snapshots.get(URL) is None


# Reaching a remote by its name


def test_a_name_reaches_its_remote_with_its_own_token_variable(
    instance: api.Azathoth,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served = Remote(tmp_path)
    instance.remotes.add("origin", URL, token_variable=SHARED_TOKEN)
    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, "azr_not_this_one")
    monkeypatch.setenv(SHARED_TOKEN, served.token)

    remote = instance.remote("origin", http=lambda: served.client)

    assert (remote.name, remote.url) == ("origin", URL)
    assert remote.capabilities().protocol == 1


def test_a_token_given_is_used_before_a_names_variable(
    instance: api.Azathoth,
    tmp_path: Path,
) -> None:
    served = Remote(tmp_path)
    instance.remotes.add("origin", URL, token_variable=SHARED_TOKEN)

    remote = instance.remote("origin", token=served.token, http=lambda: served.client)

    assert remote.capabilities().protocol == 1


def test_a_name_whose_variable_is_not_set_names_that_variable(
    instance: api.Azathoth,
) -> None:
    instance.remotes.add("origin", URL, token_variable=SHARED_TOKEN)

    with pytest.raises(api.InvalidArgumentError) as caught:
        instance.remote("origin")

    assert str(caught.value) == (
        "No remote token was given; set AZATHOTH_SHARED_TOKEN to one created on the remote with "
        "`azathoth remote token create`."
    )
    assert no_token_message(SHARED_TOKEN) == str(caught.value)


def test_a_remote_reached_by_url_has_no_name(
    instance: api.Azathoth,
) -> None:
    instance.remotes.add("origin", URL)

    assert instance.remote(URL, token="azr_token").name is None


@pytest.mark.parametrize(
    ("target", "url"),
    [
        ("origin", False),
        ("prod_2-east", False),
        ("remote.test", True),
        ("http://remote.test", True),
        ("https://remote.test", True),
        ("ftp://remote.test", True),
        ("localhost:8470", True),
        ("remotes/origin", True),
    ],
)
def test_a_target_holding_a_colon_or_slash_is_a_url(
    target: str,
    url: bool,
) -> None:
    assert is_remote_url(target) is url


def test_a_url_that_is_not_http_is_refused_not_looked_up(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidArgumentError) as caught:
        instance.remote("ftp://remote.test", token="azr_token")

    assert str(caught.value) == "Remote URL 'ftp://remote.test' is not an http or https URL."


def test_naming_a_remote_on_a_closed_instance_is_refused(
    database: Path,
) -> None:
    closed = api.open(database)
    closed.close()

    for call in (closed.remotes.list, lambda: closed.remote("origin")):
        with pytest.raises(api.InstanceClosedError):
            call()

"""Tests that the remotes an instance names are kept, in either database (ADRs 0126, 0141)."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path

import pytest

from azathoth.persistence import Database
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import (
    BOTH_TOKEN_SOURCES_MESSAGE,
    REMOTE_TABLES,
    REMOTE_TOKEN_COMMAND_TABLES,
    REMOTE_TOKEN_VARIABLE,
    InMemoryRemoteRepository,
    NamedRemote,
    RemoteAlreadyNamedError,
    RemoteNameError,
    RemoteNotNamedError,
    RemoteRepository,
    SqlRemoteRepository,
    require_remote_name,
    require_token_variable,
)

START = datetime(2026, 11, 12, 4, 0, tzinfo=UTC)

TEAM = "https://azathoth.example.com"

STAGING = "https://staging.example.com"

SHARED_TOKEN = "AZATHOTH_SHARED_TOKEN"

GCLOUD = ("gcloud", "auth", "print-identity-token", "--audiences", "https://team example")


def clock() -> Callable[[], datetime]:
    """Return a clock a minute later each time it is read."""

    minutes: Iterator[int] = count()

    return lambda: START + timedelta(minutes=next(minutes))


@pytest.fixture(params=["sql", "memory"])
def remotes(
    request: pytest.FixtureRequest,
    database: Database,
) -> RemoteRepository:
    """Open the remote repository over an initialized database, or in memory."""

    if request.param == "memory":
        return InMemoryRemoteRepository(clock=clock())

    database.initialize((*REMOTE_TABLES, *REMOTE_TOKEN_COMMAND_TABLES))

    return SqlRemoteRepository(database, clock=clock())


def test_a_remote_is_named_with_its_url_and_the_default_token_variable(
    remotes: RemoteRepository,
) -> None:
    added = remotes.add("origin", f"{TEAM}/")

    assert added == NamedRemote(
        name="origin",
        url=TEAM,
        token_variable=REMOTE_TOKEN_VARIABLE,
        added_at=START,
    )
    assert REMOTE_TOKEN_VARIABLE == "AZATHOTH_REMOTE_TOKEN"
    assert remotes.get("origin") == added


def test_a_remote_may_name_another_token_variable(
    remotes: RemoteRepository,
) -> None:
    added = remotes.add("team", TEAM, token_variable=SHARED_TOKEN)

    assert added.token_variable == SHARED_TOKEN
    assert remotes.get("team") == added


def test_a_remote_may_name_the_command_its_token_is_printed_by_instead(
    remotes: RemoteRepository,
) -> None:
    added = remotes.add("team", TEAM, token_command=list(GCLOUD))

    assert added == NamedRemote(
        name="team",
        url=TEAM,
        token_variable=None,
        token_command=GCLOUD,
        added_at=START,
    )
    assert remotes.get("team") == added


def test_a_remote_names_a_token_variable_or_a_command_never_both(
    remotes: RemoteRepository,
) -> None:
    with pytest.raises(RemoteNameError) as caught:
        remotes.add("team", TEAM, token_variable=SHARED_TOKEN, token_command=GCLOUD)

    assert str(caught.value) == BOTH_TOKEN_SOURCES_MESSAGE
    assert BOTH_TOKEN_SOURCES_MESSAGE == (
        "Give a remote a token variable or a token command, not both."
    )
    assert remotes.remotes() == ()


def test_a_named_remote_holds_a_token_variable_or_a_command_never_both_nor_neither() -> None:
    for variable, command in ((SHARED_TOKEN, GCLOUD), (None, None)):
        with pytest.raises(ValueError, match="a token variable or a token command"):
            NamedRemote(
                name="team",
                url=TEAM,
                token_variable=variable,
                token_command=command,
                added_at=START,
            )


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ((), "A token command names the program that prints the token; it was empty."),
        (
            "gcloud auth print-identity-token",
            "A token command is given as its arguments, not as one string: split it as a shell "
            "would, as shlex.split does.",
        ),
    ],
    ids=["empty", "one-string"],
)
def test_a_token_command_that_is_not_one_is_refused(
    remotes: RemoteRepository,
    command: tuple[str, ...] | str,
    message: str,
) -> None:
    with pytest.raises(RemoteNameError) as caught:
        remotes.add("team", TEAM, token_command=command)

    assert str(caught.value) == message
    assert remotes.remotes() == ()


def test_remotes_are_listed_by_name(
    remotes: RemoteRepository,
) -> None:
    assert remotes.remotes() == ()

    staging = remotes.add("staging", STAGING)
    origin = remotes.add("origin", TEAM)
    team = remotes.add("team", TEAM, token_variable=SHARED_TOKEN)
    sso = remotes.add("sso", TEAM, token_command=GCLOUD)

    assert remotes.remotes() == (origin, sso, staging, team)


def test_a_name_never_given_names_nothing(
    remotes: RemoteRepository,
) -> None:
    remotes.add("origin", TEAM)

    assert remotes.get("Origin") is None
    assert remotes.get("staging") is None


def test_a_name_already_given_is_refused_and_keeps_its_remote(
    remotes: RemoteRepository,
) -> None:
    origin = remotes.add("origin", TEAM)

    with pytest.raises(RemoteAlreadyNamedError) as caught:
        remotes.add("origin", STAGING)

    assert str(caught.value) == (
        f"Remote origin is already named, for {TEAM}; remove it first, or choose another name."
    )
    assert remotes.remotes() == (origin,)


def test_a_removed_name_is_forgotten_and_others_kept(
    remotes: RemoteRepository,
) -> None:
    origin = remotes.add("origin", TEAM)
    staging = remotes.add("staging", STAGING)

    assert remotes.remove("origin") == origin
    assert remotes.get("origin") is None
    assert remotes.remotes() == (staging,)

    again = remotes.add("origin", STAGING)

    assert again.url == STAGING


def test_a_removed_name_forgets_its_token_command(
    remotes: RemoteRepository,
) -> None:
    sso = remotes.add("sso", TEAM, token_command=GCLOUD)

    assert remotes.remove("sso") == sso

    again = remotes.add("sso", TEAM)

    assert (again.token_variable, again.token_command) == (REMOTE_TOKEN_VARIABLE, None)
    assert remotes.get("sso") == again


def test_removing_a_name_never_given_is_refused(
    remotes: RemoteRepository,
) -> None:
    with pytest.raises(RemoteNotNamedError) as caught:
        remotes.remove("origin")

    assert str(caught.value) == "No remote is named 'origin'."


@pytest.mark.parametrize(
    "name",
    [
        "",
        "a" * 65,
        "https://azathoth.example.com",
        "team remote",
        "team/remote",
        "origin:1",
        "azathoth.example.com",
    ],
    ids=["empty", "too-long", "url", "space", "slash", "colon", "host"],
)
def test_a_name_that_is_not_one_is_refused(
    remotes: RemoteRepository,
    name: str,
) -> None:
    with pytest.raises(RemoteNameError) as caught:
        remotes.add(name, TEAM)

    assert str(caught.value) == (
        f"Remote name {name!r} is not one: use 1 to 64 letters, digits, '_' or '-'."
    )
    assert remotes.remotes() == ()


def test_the_names_allowed_are_letters_digits_underscores_and_dashes() -> None:
    for name in ("origin", "a" * 64, "prod_2-east", "0"):
        assert require_remote_name(name) == name


def test_a_url_that_is_not_one_is_refused(
    remotes: RemoteRepository,
) -> None:
    with pytest.raises(RemoteNameError) as caught:
        remotes.add("origin", "azathoth.example.com")

    assert str(caught.value) == "Remote URL 'azathoth.example.com' is not an http or https URL."
    assert remotes.remotes() == ()


@pytest.mark.parametrize(
    "variable",
    ["", "1TOKEN", "TEAM-TOKEN", "TEAM_*", "TEAM TOKEN"],
    ids=["empty", "digit-first", "dash", "star", "space"],
)
def test_a_token_variable_that_is_not_one_is_refused(
    remotes: RemoteRepository,
    variable: str,
) -> None:
    with pytest.raises(RemoteNameError) as caught:
        remotes.add("origin", TEAM, token_variable=variable)

    assert str(caught.value) == (
        f"Token variable {variable!r} is not an environment variable's name: use letters, "
        "digits and '_', not beginning with a digit."
    )
    assert remotes.remotes() == ()


def test_the_token_variables_allowed_name_environment_variables() -> None:
    for variable in ("AZATHOTH_REMOTE_TOKEN", "_TOKEN", "team_token_2"):
        assert require_token_variable(variable) == variable


def test_an_instances_database_keeps_the_remotes_it_names(
    tmp_path: Path,
) -> None:
    location = tmp_path / "azathoth.db"
    added = open_repositories(location).remotes.add("origin", TEAM)
    sso = open_repositories(location).remotes.add("sso", TEAM, token_command=GCLOUD)

    assert open_repositories(location).remotes.remotes() == (added, sso)

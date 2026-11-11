"""Tests that a remote's tokens are kept as digests, in either database (ADR 0124)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from azathoth.persistence import Database
from azathoth.remote import (
    REMOTE_TOKEN_TABLES,
    RemoteTokenError,
    SqlRemoteTokenRepository,
    token_digest,
)
from azathoth.revisions import Author

ERIS = Author(name="Eris", email="eris@example.com")

START = datetime(2026, 11, 10, 21, 0, tzinfo=UTC)


class Clock:
    """A clock a minute later each time it is read."""

    def __init__(self) -> None:
        self._minutes: Iterator[int] = count()

    def __call__(self) -> datetime:
        return START + timedelta(minutes=next(self._minutes))


def secrets() -> Iterator[str]:
    for index in count(1):
        yield f"azr_secret-{index}"


@pytest.fixture
def tokens(
    database: Database,
) -> SqlRemoteTokenRepository:
    """Initialize the token table, then open the repository over it."""

    database.initialize(REMOTE_TOKEN_TABLES)
    made = secrets()

    return SqlRemoteTokenRepository(database, clock=Clock(), new_secret=lambda: next(made))


def test_a_created_token_is_shown_once_and_kept_as_its_digest(
    database: Database,
    tokens: SqlRemoteTokenRepository,
) -> None:
    issued = tokens.create("laptop", author=ERIS)

    assert issued.secret == "azr_secret-1"
    assert issued.token.name == "laptop"
    assert issued.token.author == ERIS
    assert issued.token.created_at == START
    assert issued.token.active

    with database.transaction() as session:
        rows = session.fetchall("SELECT name, digest, revoked_at FROM remote_tokens")

    assert rows == [("laptop", token_digest("azr_secret-1"), None)]
    assert tokens.tokens() == (issued.token,)


def test_a_token_is_found_by_its_secret_and_no_other(
    tokens: SqlRemoteTokenRepository,
) -> None:
    issued = tokens.create("laptop")

    assert tokens.find("azr_secret-1") == issued.token
    assert tokens.find("azr_secret-2") is None
    assert tokens.find(token_digest("azr_secret-1")) is None


def test_a_revoked_token_no_longer_authenticates_but_is_kept(
    tokens: SqlRemoteTokenRepository,
) -> None:
    issued = tokens.create("laptop", author=ERIS)
    revoked = tokens.revoke("laptop")

    assert revoked == issued.token.model_copy(update={"revoked_at": START + timedelta(minutes=1)})
    assert not revoked.active
    assert tokens.find("azr_secret-1") is None
    assert tokens.tokens() == ()
    assert tokens.tokens(include_revoked=True) == (revoked,)


def test_an_active_name_is_not_given_twice_but_a_revoked_one_may_be(
    tokens: SqlRemoteTokenRepository,
) -> None:
    first = tokens.create("laptop")

    with pytest.raises(RemoteTokenError) as caught:
        tokens.create("laptop")

    assert str(caught.value) == (
        "A remote token named 'laptop' already exists; revoke it first, or choose another name."
    )

    tokens.revoke("laptop")
    second = tokens.create("laptop")

    assert second.secret == "azr_secret-3"
    assert tokens.tokens() == (second.token,)
    assert [token.id for token in tokens.tokens(include_revoked=True)] == [
        first.token.id,
        second.token.id,
    ]


def test_revoking_a_name_no_active_token_has_is_refused(
    tokens: SqlRemoteTokenRepository,
) -> None:
    with pytest.raises(RemoteTokenError) as caught:
        tokens.revoke("laptop")

    assert str(caught.value) == "No remote token is named 'laptop'."

    tokens.create("laptop")
    tokens.revoke("laptop")

    with pytest.raises(RemoteTokenError):
        tokens.revoke("laptop")


def test_tokens_are_listed_oldest_first(
    tokens: SqlRemoteTokenRepository,
) -> None:
    for name in ("ci", "laptop", "fargate"):
        tokens.create(name)

    assert [token.name for token in tokens.tokens()] == ["ci", "laptop", "fargate"]

"""Tests for the tokens a remote issues, and the authenticator that reads them (ADR 0124)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.remote import (
    BEARER_SCHEME,
    TOKEN_PREFIX,
    Principal,
    RemoteToken,
    RemoteTokenError,
    SQLiteRemoteTokenRepository,
    TokenAuthenticator,
    new_token_secret,
    require_token_name,
    token_digest,
)


@pytest.fixture
def tokens(
    tmp_path: Path,
) -> SQLiteRemoteTokenRepository:
    return SQLiteRemoteTokenRepository(tmp_path / "azathoth.db")


# Secrets


def test_a_token_is_prefixed_and_random() -> None:
    first = new_token_secret()

    assert TOKEN_PREFIX == "azr_"
    assert first.startswith("azr_")
    assert len(first) == len("azr_") + 43
    assert first != new_token_secret()


def test_a_token_is_kept_as_its_sha256_digest() -> None:
    assert token_digest("azr_example") == (
        "0d59637537204629e8be4fbd931ac1ce457e267c2f56c4a084f775d3a3419e2a"
    )


# Names


@pytest.mark.parametrize("name", ["laptop", "ci.prod-2", "a" * 64, "Fargate_1"])
def test_a_name_of_letters_digits_dots_underscores_and_dashes_is_accepted(
    name: str,
) -> None:
    assert require_token_name(name) == name


@pytest.mark.parametrize("name", ["", "a" * 65, "my laptop", "laptop\n", "ci/prod", "ñ"])
def test_any_other_name_is_refused(
    name: str,
    tokens: SQLiteRemoteTokenRepository,
) -> None:
    with pytest.raises(RemoteTokenError) as caught:
        require_token_name(name)

    assert str(caught.value) == (
        f"Remote token name {name!r} is not one: use 1 to 64 letters, digits, '.', '_' or '-'."
    )

    with pytest.raises(RemoteTokenError):
        tokens.create(name)

    assert tokens.tokens(include_revoked=True) == ()


def test_a_token_record_holds_only_an_allowed_name(
    tokens: SQLiteRemoteTokenRepository,
) -> None:
    token = tokens.create("laptop").token

    with pytest.raises(ValidationError):
        RemoteToken.model_validate({**token.model_dump(mode="json"), "name": "my laptop"})


# Authenticating


def test_an_active_tokens_bearer_is_the_owner(
    tokens: SQLiteRemoteTokenRepository,
) -> None:
    secret = tokens.create("laptop").secret
    authenticator = TokenAuthenticator(tokens)

    assert BEARER_SCHEME == "bearer"
    assert authenticator.authenticate(f"Bearer {secret}") == Principal(name="laptop", owner=True)
    assert authenticator.authenticate(f"bearer  {secret} ") == Principal(name="laptop", owner=True)


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer",
        "Bearer ",
        "Basic {secret}",
        "{secret}",
        "Bearer azr_another",
        "Bearer {digest}",
    ],
    ids=["absent", "empty", "no-token", "blank-token", "basic", "bare", "unknown", "digest"],
)
def test_anything_else_names_no_one(
    tokens: SQLiteRemoteTokenRepository,
    header: str | None,
) -> None:
    secret = tokens.create("laptop").secret
    given = None if header is None else header.format(secret=secret, digest=token_digest(secret))

    assert TokenAuthenticator(tokens).authenticate(given) is None


def test_a_revoked_tokens_bearer_is_no_one(
    tokens: SQLiteRemoteTokenRepository,
) -> None:
    secret = tokens.create("laptop").secret
    tokens.revoke("laptop")

    assert TokenAuthenticator(tokens).authenticate(f"Bearer {secret}") is None

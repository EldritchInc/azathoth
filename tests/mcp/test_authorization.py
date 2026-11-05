"""Tests for verifying bearer tokens as a resource server (ADR 0111)."""

import asyncio
import logging
import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from mcp.server.auth.provider import AccessToken
from pydantic import ValidationError

from azathoth_mcp.access import McpCaller, Transport
from azathoth_mcp.authorization import (
    ASYMMETRIC_ALGORITHMS,
    DEFAULT_ALGORITHMS,
    AuthorizationConfigurationError,
    AuthorizationSettings,
    JwtTokenVerifier,
    discover_jwks_url,
    http_caller,
    token_client_id,
    token_scopes,
)

ISSUER = "https://idp.example.com/tenant"

RESOURCE = "https://mcp.example.com/mcp"

RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

OTHER_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

EC_KEY = ec.generate_private_key(ec.SECP256R1())


class StaticKeys:
    """One public key, whichever token asks."""

    def __init__(
        self,
        key: Any,
    ) -> None:
        self.key = key

    def key_for(
        self,
        token: str,
    ) -> Any:
        """Return the one public key."""

        return self.key


def claims(
    **changes: Any,
) -> dict[str, Any]:
    """Return a valid token's claims, with some changed; a `None` removes a claim."""

    now = int(time.time())
    values: dict[str, Any] = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": "alice",
        "iat": now,
        "exp": now + 300,
        "scope": "azathoth:invoke:summarize azathoth:read",
        "azp": "claude-desktop",
    }
    values.update(changes)

    return {name: value for name, value in values.items() if value is not None}


def token(
    payload: dict[str, Any] | None = None,
    *,
    key: Any = RSA_KEY,
    algorithm: str = "RS256",
) -> str:
    """Return a signed token."""

    return jwt.encode(payload if payload is not None else claims(), key, algorithm=algorithm)


def settings(
    **changes: Any,
) -> AuthorizationSettings:
    """Return authorization settings for the test issuer and resource."""

    return AuthorizationSettings(issuer=ISSUER, resource=RESOURCE, **changes)


def verify(
    raw: str,
    *,
    configured: AuthorizationSettings | None = None,
    key: Any = None,
) -> AccessToken | None:
    """Verify one token with a verifier that trusts one key."""

    verifier = JwtTokenVerifier(
        configured if configured is not None else settings(),
        StaticKeys(key if key is not None else RSA_KEY.public_key()),
    )

    return asyncio.run(verifier.verify_token(raw))


# Accepted tokens


def test_a_valid_token_grants_its_scopes_to_its_subject() -> None:
    payload = claims()
    raw = token(payload)
    access = verify(raw)

    assert access is not None
    assert access.subject == "alice"
    assert access.client_id == "claude-desktop"
    assert access.scopes == ["azathoth:invoke:summarize", "azathoth:read"]
    assert access.resource == RESOURCE
    assert access.expires_at == payload["exp"]
    assert access.claims == {"iss": ISSUER}
    assert access.token == raw


def test_an_audience_list_holding_the_resource_is_accepted() -> None:
    access = verify(token(claims(aud=["https://other.example.com", RESOURCE])))

    assert access is not None


def test_an_elliptic_curve_signature_is_accepted() -> None:
    access = verify(token(key=EC_KEY, algorithm="ES256"), key=EC_KEY.public_key())

    assert access is not None


def test_a_token_within_the_clocks_leeway_is_accepted() -> None:
    now = int(time.time())

    assert verify(token(claims(exp=now - 10, iat=now - 310))) is not None


def test_a_token_within_the_maximum_lifetime_is_accepted() -> None:
    now = int(time.time())

    access = verify(
        token(claims(iat=now, exp=now + 600)),
        configured=settings(max_lifetime_seconds=600),
    )

    assert access is not None


# Refused tokens


@pytest.mark.parametrize(
    "payload",
    [
        claims(aud="https://other.example.com/mcp"),
        claims(aud="https://mcp.example.com/mcp/"),
        claims(iss="https://idp.example.com/other"),
        claims(exp=int(time.time()) - 120),
        claims(exp=None),
        claims(iss=None),
        claims(aud=None),
        claims(sub=None),
        claims(sub=""),
        claims(sub=42),
        claims(nbf=int(time.time()) + 600),
    ],
    ids=[
        "another-audience",
        "a-different-spelling-of-the-audience",
        "another-issuer",
        "expired",
        "no-expiry",
        "no-issuer",
        "no-audience",
        "no-subject",
        "empty-subject",
        "non-text-subject",
        "not-yet-valid",
    ],
)
def test_a_token_this_server_did_not_get_is_refused(
    payload: dict[str, Any],
) -> None:
    assert verify(token(payload)) is None


def test_a_token_signed_by_another_key_is_refused() -> None:
    assert verify(token(key=OTHER_RSA_KEY)) is None


def test_a_token_signed_by_an_algorithm_not_allowed_is_refused() -> None:
    raw = token(key=EC_KEY, algorithm="ES256")

    assert verify(raw, configured=settings(algorithms=("RS256",)), key=EC_KEY.public_key()) is None


def test_a_token_signed_with_a_shared_secret_is_refused() -> None:
    secret = jwt.encode(claims(), "a-shared-secret-of-at-least-32-bytes!", algorithm="HS256")

    assert verify(secret) is None


def test_an_unsigned_token_is_refused() -> None:
    unsigned = jwt.encode(claims(), "", algorithm="none")

    assert verify(unsigned) is None


@pytest.mark.parametrize("raw", ["", "not-a-token", "a.b.c"])
def test_something_that_is_not_a_token_is_refused(
    raw: str,
) -> None:
    assert verify(raw) is None


def test_a_token_living_longer_than_allowed_is_refused() -> None:
    now = int(time.time())

    assert (
        verify(token(claims(iat=now, exp=now + 601)), configured=settings(max_lifetime_seconds=600))
        is None
    )


def test_a_maximum_lifetime_needs_the_time_a_token_was_issued() -> None:
    assert verify(token(claims(iat=None)), configured=settings(max_lifetime_seconds=600)) is None
    assert verify(token(claims(iat=None))) is not None


def test_a_refusal_is_logged_by_kind_and_never_with_the_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = token(claims(aud="https://other.example.com/mcp"))

    with caplog.at_level(logging.DEBUG):
        assert verify(raw) is None

    assert "A bearer token was refused: InvalidAudienceError." in caplog.text
    assert raw not in caplog.text

    for part in raw.split("."):
        assert part not in caplog.text


# Scopes, clients and callers


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"scope": "a b  c"}, ("a", "b", "c")),
        ({"scp": "a b"}, ("a", "b")),
        ({"scp": ["a", "b"]}, ("a", "b")),
        ({"scope": "a", "scp": "b"}, ("a",)),
        ({"scope": 5, "scp": ["b"]}, ("b",)),
        ({"scp": ["a", 1]}, ()),
        ({}, ()),
    ],
)
def test_scopes_are_read_from_scope_or_scp(
    payload: dict[str, Any],
    expected: tuple[str, ...],
) -> None:
    assert token_scopes(payload) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"client_id": "a", "azp": "b"}, "a"),
        ({"azp": "b", "appid": "c"}, "b"),
        ({"appid": "c"}, "c"),
        ({"client_id": "", "azp": "b"}, "b"),
        ({}, ""),
    ],
)
def test_the_client_is_read_from_the_first_claim_naming_it(
    payload: dict[str, Any],
    expected: str,
) -> None:
    assert token_client_id(payload) == expected


def test_a_token_without_a_client_grants_access_without_one() -> None:
    access = verify(token(claims(azp=None)))

    assert access is not None
    assert access.client_id == ""
    assert http_caller(access).client_id is None


def test_a_token_becomes_its_caller() -> None:
    access = verify(token())

    assert http_caller(access) == McpCaller(
        transport=Transport.HTTP,
        subject="alice",
        client_id="claude-desktop",
        scopes=frozenset({"azathoth:invoke:summarize", "azathoth:read"}),
    )


def test_no_token_is_the_unauthorized_local_caller() -> None:
    assert http_caller(None) == McpCaller(transport=Transport.HTTP)
    assert http_caller(None).scopes is None


# Settings


def test_the_defaults_accept_rsa_and_elliptic_curve_signatures() -> None:
    configured = settings()

    assert configured.algorithms == DEFAULT_ALGORITHMS == ("RS256", "ES256")
    assert configured.leeway_seconds == 30
    assert configured.max_lifetime_seconds is None
    assert set(DEFAULT_ALGORITHMS) <= ASYMMETRIC_ALGORITHMS


@pytest.mark.parametrize(
    "url",
    [
        "http://idp.example.com/tenant",
        "https://idp.example.com/tenant?x=1",
        "https://idp.example.com/tenant#x",
        "ftp://idp.example.com",
        "idp.example.com",
    ],
)
def test_an_issuer_must_be_https(
    url: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        AuthorizationSettings(issuer=url, resource=RESOURCE)

    assert raised.value.errors()[0]["msg"] == (
        f"Value error, {url} must be an HTTPS URL, or an HTTP URL on a loopback address, "
        "with no query or fragment."
    )


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8000/mcp", "http://localhost/mcp", "http://[::1]:9000/mcp"],
)
def test_http_is_allowed_on_a_loopback_address(
    url: str,
) -> None:
    assert AuthorizationSettings(issuer=ISSUER, resource=url).resource == url


def test_the_keys_url_must_be_https_too() -> None:
    with pytest.raises(ValidationError):
        settings(jwks_url="http://idp.example.com/keys")


@pytest.mark.parametrize(
    ("algorithms", "message"),
    [
        ((), "At least one signing algorithm must be allowed."),
        (
            ("RS256", "HS256", "none"),
            "Only public-key signing algorithms may be allowed; not HS256, none.",
        ),
    ],
)
def test_only_public_key_algorithms_may_be_allowed(
    algorithms: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        settings(algorithms=algorithms)

    assert raised.value.errors()[0]["msg"] == f"Value error, {message}"


@pytest.mark.parametrize("seconds", [0, -1])
def test_a_maximum_lifetime_is_positive(
    seconds: int,
) -> None:
    with pytest.raises(ValidationError):
        settings(max_lifetime_seconds=seconds)


# Discovering keys


def metadata_client(
    documents: dict[str, Any],
) -> httpx.Client:
    """Return an HTTP client that answers from some documents by path, and 404 otherwise."""

    def answer(
        request: httpx.Request,
    ) -> httpx.Response:
        document = documents.get(request.url.path)

        if document is None:
            return httpx.Response(404)

        if isinstance(document, str):
            return httpx.Response(200, text=document)

        return httpx.Response(200, json=document)

    return httpx.Client(transport=httpx.MockTransport(answer))


def test_keys_are_found_in_the_openid_configuration() -> None:
    client = metadata_client(
        {
            "/tenant/.well-known/openid-configuration": {"jwks_uri": "https://idp/oidc-keys"},
            "/tenant/.well-known/oauth-authorization-server": {"jwks_uri": "https://idp/as-keys"},
        }
    )

    assert discover_jwks_url(ISSUER, client=client) == "https://idp/oidc-keys"


def test_metadata_that_is_not_served_successfully_is_not_used() -> None:
    def answer(
        request: httpx.Request,
    ) -> httpx.Response:
        if request.url.path.endswith("/openid-configuration"):
            return httpx.Response(500, json={"jwks_uri": "https://idp/error-keys"})

        return httpx.Response(200, json={"jwks_uri": "https://idp/as-keys"})

    client = httpx.Client(transport=httpx.MockTransport(answer))

    assert discover_jwks_url(ISSUER, client=client) == "https://idp/as-keys"


def test_keys_are_found_in_the_authorization_server_metadata_otherwise() -> None:
    client = metadata_client(
        {
            "/tenant/.well-known/openid-configuration": "not json",
            "/tenant/.well-known/oauth-authorization-server": {"jwks_uri": "https://idp/as-keys"},
        }
    )

    assert discover_jwks_url(ISSUER + "/", client=client) == "https://idp/as-keys"


@pytest.mark.parametrize(
    "documents",
    [
        {},
        {"/tenant/.well-known/openid-configuration": {"issuer": ISSUER}},
        {"/tenant/.well-known/openid-configuration": ["jwks_uri"]},
        {"/tenant/.well-known/openid-configuration": {"jwks_uri": ""}},
    ],
)
def test_an_issuer_whose_keys_cannot_be_found_stops_the_server(
    documents: dict[str, Any],
) -> None:
    with pytest.raises(AuthorizationConfigurationError) as raised:
        discover_jwks_url(ISSUER, client=metadata_client(documents))

    assert str(raised.value) == (
        f"Cannot find the signing keys of {ISSUER}: neither its OpenID Connect nor its "
        "OAuth metadata names a jwks_uri. Name them with --jwks-url."
    )


def test_an_issuer_that_cannot_be_reached_stops_the_server() -> None:
    def unreachable(
        request: httpx.Request,
    ) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(AuthorizationConfigurationError):
        discover_jwks_url(ISSUER, client=httpx.Client(transport=httpx.MockTransport(unreachable)))

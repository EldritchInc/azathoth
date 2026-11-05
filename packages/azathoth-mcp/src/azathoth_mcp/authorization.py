"""Authorizing HTTP callers: an OAuth 2.1 resource server (ADR 0111).

The server issues no tokens and signs no one in; the organization's
identity provider does. Every request carries a bearer token, a signed JWT,
which the server accepts only when all of these hold:

- it is signed, by an algorithm on the allow-list, with one of the
  provider's published keys;
- its issuer is the provider's;
- its audience holds this server's own resource URL (RFC 8707), so a token
  issued for another service is refused;
- it has an expiry, and has not expired; with a maximum lifetime set, it
  also says when it was issued, and lives no longer than that;
- it names its subject.

The token's scopes, from `scope` or `scp`, decide what the caller may call
(`azathoth_mcp.access`). A token is never logged, never passed on, and never
kept beyond its request.
"""

import asyncio
import logging
import re
from collections.abc import Mapping
from typing import Any, Protocol

import httpx
import jwt
from mcp.server.auth.provider import AccessToken
from pydantic import BaseModel, ConfigDict, Field, field_validator

from azathoth_mcp.access import McpCaller, Transport

DEFAULT_ALGORITHMS = ("RS256", "ES256")
"""The signing algorithms accepted unless the operator names others."""

ASYMMETRIC_ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
)
"""The algorithms an operator may allow: public-key ones only, never `none` or HMAC."""

DEFAULT_LEEWAY_SECONDS = 30
"""How far apart the server's clock and the provider's may be."""

DISCOVERY_PATHS = (
    "/.well-known/openid-configuration",
    "/.well-known/oauth-authorization-server",
)
"""Where an issuer's metadata names its keys, OpenID Connect's first (RFC 8414)."""

HTTPS_URL = re.compile(r"https://[^\s/?#]+(?:/[^\s?#]*)?")

LOOPBACK_HTTP_URL = re.compile(r"http://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?(?:/[^\s?#]*)?")

logger = logging.getLogger(__name__)


class AuthorizationConfigurationError(ValueError):
    """Raised when the server cannot be set up to authorize its callers."""


class AuthorizationSettings(BaseModel):
    """How one server authorizes its HTTP callers.

    `issuer` is the identity provider's issuer, exactly as its tokens carry
    it. `resource` is this server's own URL, the one clients connect to and
    tokens must name as their audience. Both are HTTPS, or HTTP on a loopback
    address for testing.
    """

    model_config = ConfigDict(frozen=True)

    issuer: str
    resource: str
    jwks_url: str | None = None
    algorithms: tuple[str, ...] = DEFAULT_ALGORITHMS
    max_lifetime_seconds: int | None = Field(default=None, gt=0)
    leeway_seconds: int = Field(default=DEFAULT_LEEWAY_SECONDS, ge=0)

    @field_validator("issuer", "resource", "jwks_url")
    @classmethod
    def require_secure_url(
        cls,
        url: str | None,
    ) -> str | None:
        """Refuse a URL that is not HTTPS, unless it is HTTP on a loopback address."""

        if url is None:
            return None

        if HTTPS_URL.fullmatch(url) is None and LOOPBACK_HTTP_URL.fullmatch(url) is None:
            raise ValueError(
                f"{url} must be an HTTPS URL, or an HTTP URL on a loopback address, "
                "with no query or fragment."
            )

        return url

    @field_validator("algorithms")
    @classmethod
    def require_public_key_algorithms(
        cls,
        algorithms: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Refuse an empty allow-list, and any algorithm that is not public-key."""

        if not algorithms:
            raise ValueError("At least one signing algorithm must be allowed.")

        refused = sorted(set(algorithms) - ASYMMETRIC_ALGORITHMS)

        if refused:
            raise ValueError(
                "Only public-key signing algorithms may be allowed; not " + ", ".join(refused) + "."
            )

        return algorithms


class SigningKeys(Protocol):
    """Where a verifier finds the key that signed one token."""

    def key_for(
        self,
        token: str,
    ) -> Any:
        """Return the public key that signed one token.

        Raises:
            jwt.PyJWTError: No published key signed it, or the keys cannot be read.
        """

        ...


class PublishedKeys:
    """An identity provider's published keys (its JWKS), cached and refreshed as keys rotate."""

    def __init__(
        self,
        jwks_url: str,
    ) -> None:
        self._client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=10)

    def key_for(
        self,
        token: str,
    ) -> Any:
        """Return the published key named by one token's `kid`."""

        return self._client.get_signing_key_from_jwt(token).key


def discover_jwks_url(
    issuer: str,
    *,
    client: httpx.Client | None = None,
) -> str:
    """Return the URL of an issuer's published keys, from its metadata.

    Raises:
        AuthorizationConfigurationError: Neither metadata document can be
            read, or neither names its keys.
    """

    owned = client is None
    http = client if client is not None else httpx.Client(timeout=10)

    try:
        for path in DISCOVERY_PATHS:
            try:
                response = http.get(issuer.rstrip("/") + path)
            except httpx.HTTPError:
                continue

            if response.status_code != 200:
                continue

            try:
                metadata = response.json()
            except ValueError:
                continue

            jwks_url = metadata.get("jwks_uri") if isinstance(metadata, dict) else None

            if isinstance(jwks_url, str) and jwks_url:
                return jwks_url
    finally:
        if owned:
            http.close()

    raise AuthorizationConfigurationError(
        f"Cannot find the signing keys of {issuer}: neither its OpenID Connect nor its "
        "OAuth metadata names a jwks_uri. Name them with --jwks-url."
    )


def token_scopes(
    claims: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return a token's scopes, from `scope` or, as some providers write it, `scp`.

    Either may be one space-separated string or a list of strings.
    """

    for name in ("scope", "scp"):
        value = claims.get(name)

        if isinstance(value, str):
            return tuple(value.split())

        if isinstance(value, list) and all(isinstance(scope, str) for scope in value):
            return tuple(value)

    return ()


def token_client_id(
    claims: Mapping[str, Any],
) -> str:
    """Return the client a token was issued to, or an empty string if it names none."""

    for name in ("client_id", "azp", "appid"):
        value = claims.get(name)

        if isinstance(value, str) and value:
            return value

    return ""


class JwtTokenVerifier:
    """Verify bearer tokens as signed JWTs, as the SDK's bearer middleware asks."""

    def __init__(
        self,
        settings: AuthorizationSettings,
        keys: SigningKeys,
    ) -> None:
        self._settings = settings
        self._keys = keys

    async def verify_token(
        self,
        token: str,
    ) -> AccessToken | None:
        """Return the access a valid token grants, or `None` for any other.

        Why a token was refused is logged by kind, never with the token.
        """

        try:
            claims = await asyncio.to_thread(self._claims, token)
        except jwt.PyJWTError as exc:
            logger.info("A bearer token was refused: %s.", type(exc).__name__)

            return None

        return AccessToken(
            token=token,
            client_id=token_client_id(claims),
            scopes=list(token_scopes(claims)),
            expires_at=int(claims["exp"]),
            resource=self._settings.resource,
            subject=str(claims["sub"]),
            claims={"iss": claims["iss"]},
        )

    def _claims(
        self,
        token: str,
    ) -> dict[str, Any]:
        """Return one token's verified claims.

        Raises:
            jwt.PyJWTError: The token is not one this server accepts.
        """

        settings = self._settings
        required = ["exp", "iss", "aud", "sub"]

        if settings.max_lifetime_seconds is not None:
            required.append("iat")

        claims: dict[str, Any] = jwt.decode(
            token,
            self._keys.key_for(token),
            algorithms=list(settings.algorithms),
            audience=settings.resource,
            issuer=settings.issuer,
            leeway=settings.leeway_seconds,
            options={"require": required},
        )

        if settings.max_lifetime_seconds is not None:
            lifetime = int(claims["exp"]) - int(claims["iat"])

            if lifetime > settings.max_lifetime_seconds:
                raise jwt.InvalidTokenError("The token lives longer than this server allows.")

        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise jwt.MissingRequiredClaimError("sub")

        return claims


def http_caller(
    access: AccessToken | None,
) -> McpCaller:
    """Return the caller one HTTP request comes from.

    A request without a token reaches the server only when it runs without
    authorization, on a loopback address; that caller may call everything,
    as the local caller over stdio may.
    """

    if access is None:
        return McpCaller(transport=Transport.HTTP)

    return McpCaller(
        transport=Transport.HTTP,
        subject=access.subject or None,
        client_id=access.client_id or None,
        scopes=frozenset(access.scopes),
    )


__all__ = [
    "ASYMMETRIC_ALGORITHMS",
    "DEFAULT_ALGORITHMS",
    "DEFAULT_LEEWAY_SECONDS",
    "DISCOVERY_PATHS",
    "AuthorizationConfigurationError",
    "AuthorizationSettings",
    "JwtTokenVerifier",
    "PublishedKeys",
    "SigningKeys",
    "discover_jwks_url",
    "http_caller",
    "token_client_id",
    "token_scopes",
]

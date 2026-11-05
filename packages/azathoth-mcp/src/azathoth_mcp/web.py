"""Serving over Streamable HTTP (ADR 0111).

The server is one ASGI application with two routes:

- the MCP endpoint, `/mcp`, which every request reaches only with a valid
  bearer token when the server authorizes its callers;
- the Protected Resource Metadata (RFC 9728), at
  `/.well-known/oauth-protected-resource/mcp`, which names the identity
  provider and every scope the server's tools need, so a client knows where
  to get a token and what to ask for. An unauthenticated request is answered
  with a 401 that points to it.

The endpoint is stateless: each request is served on its own, under its
own token, and a call's progress is streamed back in its own response.
Every request's `Host` header must be one the server answers to, and an
`Origin` header, which browsers send, one it allows, so a web page cannot
reach a server through DNS rebinding.

Without authorization, the server binds only to a loopback address.
"""

import ipaddress
from collections.abc import Sequence
from urllib.parse import urlsplit

from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.routes import build_resource_metadata_url, create_protected_resource_routes
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Route

from azathoth_mcp.access import READ_ALL_SCOPE, READ_SCOPE, invoke_scope
from azathoth_mcp.authorization import AuthorizationSettings
from azathoth_mcp.catalog import ToolCatalog

MCP_PATH = "/mcp"

RESOURCE_NAME = "Azathoth"

LOOPBACK_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")

LOOPBACK_ORIGINS = ("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*")


class UnprotectedBindError(ValueError):
    """Raised when a server without authorization would listen beyond loopback."""


def is_loopback(
    host: str,
) -> bool:
    """Report whether one bind address is a loopback address, given as an IP literal."""

    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def require_protection(
    host: str,
    authorization: AuthorizationSettings | None,
) -> None:
    """Refuse to serve without authorization anywhere but a loopback address.

    Raises:
        UnprotectedBindError: There is no authorization, and the host is not
            a loopback IP address.
    """

    if authorization is None and not is_loopback(host):
        raise UnprotectedBindError(
            "Without --issuer and --resource, the server authorizes no one, so it listens "
            f"only on a loopback address, such as 127.0.0.1 or ::1; got --host {host}."
        )


def scopes_supported(
    catalog: ToolCatalog,
) -> list[str]:
    """Return every scope the server's tools may need, as its metadata advertises them."""

    return [
        *(invoke_scope(tool.name) for tool in catalog.exposure.tools),
        READ_SCOPE,
        READ_ALL_SCOPE,
    ]


def transport_security(
    authorization: AuthorizationSettings | None,
    *,
    allowed_hosts: Sequence[str] = (),
    allowed_origins: Sequence[str] = (),
) -> TransportSecuritySettings:
    """Return the `Host` and `Origin` checks of one server.

    A server without authorization answers loopback names and origins. One
    with authorization answers its resource URL's host, and any the operator
    adds, such as a load balancer's.
    """

    if authorization is None:
        hosts = [*LOOPBACK_HOSTS, *allowed_hosts]
        origins = [*LOOPBACK_ORIGINS, *allowed_origins]
    else:
        hosts = [urlsplit(authorization.resource).netloc, *allowed_hosts]
        origins = list(allowed_origins)

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


def http_app(
    server: Server[object],
    catalog: ToolCatalog,
    *,
    authorization: AuthorizationSettings | None,
    verifier: TokenVerifier | None,
    allowed_hosts: Sequence[str] = (),
    allowed_origins: Sequence[str] = (),
) -> Starlette:
    """Return the ASGI application that serves one server over Streamable HTTP.

    With authorization, a verifier is required, and every request to the
    MCP endpoint must carry a token it accepts.

    Raises:
        ValueError: Authorization is given without a verifier, or a verifier
            without authorization.
    """

    if (authorization is None) != (verifier is None):
        raise ValueError("Authorization and a token verifier are given together, or neither.")

    sessions = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        security_settings=transport_security(
            authorization,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
    )
    endpoint = StreamableHTTPASGIApp(sessions)

    if authorization is None or verifier is None:
        return Starlette(
            routes=[Route(MCP_PATH, endpoint=endpoint)],
            lifespan=lambda app: sessions.run(),
        )

    resource = AnyHttpUrl(authorization.resource)

    return Starlette(
        routes=[
            Route(
                MCP_PATH,
                endpoint=RequireAuthMiddleware(
                    endpoint,
                    required_scopes=[],
                    resource_metadata_url=build_resource_metadata_url(resource),
                ),
            ),
            *create_protected_resource_routes(
                resource_url=resource,
                authorization_servers=[AnyHttpUrl(authorization.issuer)],
                scopes_supported=scopes_supported(catalog),
                resource_name=RESOURCE_NAME,
            ),
        ],
        middleware=[
            Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(verifier)),
            Middleware(AuthContextMiddleware),
        ],
        lifespan=lambda app: sessions.run(),
    )


__all__ = [
    "LOOPBACK_HOSTS",
    "LOOPBACK_ORIGINS",
    "MCP_PATH",
    "RESOURCE_NAME",
    "UnprotectedBindError",
    "http_app",
    "is_loopback",
    "require_protection",
    "scopes_supported",
    "transport_security",
]

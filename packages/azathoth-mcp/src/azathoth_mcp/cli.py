"""The `azathoth-mcp` command (ADR 0111).

`azathoth-mcp serve` reads the same environment as the `azathoth` CLI, for
its database and its models' credentials, and the exposure document that
`--exposure` or `AZATHOTH_MCP_EXPOSURE` names. Before it serves anything it
checks that every exposed workflow is active in production, and composes
its runtime, so a document, a database or a provider that cannot be used
stops it with one line on stderr and status 1, before any client connects.

It serves one local client over stdio, the default, or any number over
Streamable HTTP with `--transport http`. Over HTTP, `--issuer` and
`--resource` make it an OAuth 2.1 resource server in front of the
organization's identity provider; without them it authorizes no one, and
listens only on a loopback address.

Over stdio, standard output carries the protocol and nothing else; every
message the command writes goes to standard error.
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError
from starlette.applications import Starlette

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.persistence import repositories
from azathoth.cli.streams import use_utf8_streams
from azathoth.cli.termination import (
    INTERRUPTED_MESSAGE,
    INTERRUPTED_STATUS,
    TERMINATED_MESSAGE,
    TERMINATED_STATUS,
    CommandTerminated,
    terminating_on_sigterm,
)
from azathoth.cli.tracing import run_traced
from azathoth.inputs import ContentStoreError
from azathoth.persistence import DatabaseSchemaError, DatabaseUnavailableError
from azathoth.persistence.repositories import close_postgres_databases
from azathoth.providers import (
    BedrockConfigurationError,
    BedrockUnavailableError,
    ModelDiscoveryError,
)
from azathoth.telemetry import Telemetry
from azathoth_mcp import __version__
from azathoth_mcp.access import STDIO_CALLER
from azathoth_mcp.authorization import (
    DEFAULT_ALGORITHMS,
    AuthorizationConfigurationError,
    AuthorizationSettings,
    JwtTokenVerifier,
    PublishedKeys,
    discover_jwks_url,
    http_caller,
)
from azathoth_mcp.catalog import ToolCatalog, check_exposure
from azathoth_mcp.exposure import ExposureDocumentError, load_exposure
from azathoth_mcp.server import build_server
from azathoth_mcp.service import ToolService
from azathoth_mcp.web import MCP_PATH, UnprotectedBindError, http_app, require_protection

PROGRAM = "azathoth-mcp"

EXPOSURE_ENVIRONMENT_VARIABLE = "AZATHOTH_MCP_EXPOSURE"

STDIO_TRANSPORT = "stdio"

HTTP_TRANSPORT = "http"

TRANSPORTS = (STDIO_TRANSPORT, HTTP_TRANSPORT)

DEFAULT_HOST = "127.0.0.1"

DEFAULT_PORT = 8000

HTTP_OPTIONS = (
    "host",
    "port",
    "issuer",
    "resource",
    "jwks_url",
    "algorithm",
    "max_token_lifetime",
    "allowed_host",
    "allowed_origin",
)
"""The options that mean something only over HTTP."""

NO_EXPOSURE_MESSAGE = (
    f"Name the exposure document to serve with --exposure or {EXPOSURE_ENVIRONMENT_VARIABLE}."
)

STARTUP_ERRORS = (
    ExposureDocumentError,
    AuthorizationConfigurationError,
    DatabaseUnavailableError,
    DatabaseSchemaError,
    ContentStoreError,
    BedrockUnavailableError,
    BedrockConfigurationError,
    ModelDiscoveryError,
)
"""What stops the server before it serves, each reported in one line."""


def build_parser() -> argparse.ArgumentParser:
    """Return the parser of the `azathoth-mcp` command line."""

    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Serve promoted Azathoth workflows as Model Context Protocol tools.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROGRAM} {__version__}",
    )

    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    serve = commands.add_parser(
        "serve",
        help="Serve the exposed workflows.",
        description="Serve the workflows an exposure document lists, as MCP tools.",
    )
    serve.add_argument(
        "--exposure",
        type=Path,
        metavar="PATH",
        help=f"The exposure document to serve. Defaults to {EXPOSURE_ENVIRONMENT_VARIABLE}.",
    )
    serve.add_argument(
        "--transport",
        choices=TRANSPORTS,
        default=STDIO_TRANSPORT,
        help="How clients reach the server. Defaults to stdio.",
    )

    http = serve.add_argument_group("HTTP", "Options of --transport http.")
    http.add_argument(
        "--host",
        help=f"The address to listen on. Defaults to {DEFAULT_HOST}.",
    )
    http.add_argument(
        "--port",
        type=int,
        help=f"The port to listen on. Defaults to {DEFAULT_PORT}.",
    )
    http.add_argument(
        "--issuer",
        metavar="URL",
        help="The identity provider's issuer, exactly as its tokens carry it.",
    )
    http.add_argument(
        "--resource",
        metavar="URL",
        help="This server's URL, ending in /mcp, which tokens must name as their audience.",
    )
    http.add_argument(
        "--jwks-url",
        metavar="URL",
        help="Where the provider publishes its signing keys. Defaults to its metadata's.",
    )
    http.add_argument(
        "--algorithm",
        action="append",
        metavar="NAME",
        help="A signing algorithm to accept; repeat for more. Defaults to "
        + " and ".join(DEFAULT_ALGORITHMS)
        + ".",
    )
    http.add_argument(
        "--max-token-lifetime",
        type=int,
        metavar="SECONDS",
        help="Refuse tokens issued to live longer than this.",
    )
    http.add_argument(
        "--allowed-host",
        action="append",
        metavar="HOST",
        help="Another Host header to answer, such as a load balancer's; repeat for more.",
    )
    http.add_argument(
        "--allowed-origin",
        action="append",
        metavar="ORIGIN",
        help="A browser Origin to allow; repeat for more.",
    )

    return parser


def authorization_settings(
    arguments: argparse.Namespace,
) -> AuthorizationSettings | None:
    """Return the authorization the command line asks for, or `None` for none.

    Raises:
        ValueError: Only one of `--issuer` and `--resource` is given, or the
            settings are not valid. The message says why.
    """

    if (arguments.issuer is None) != (arguments.resource is None):
        raise ValueError("Name both --issuer and --resource, or neither.")

    if arguments.issuer is None:
        for name in ("jwks_url", "algorithm", "max_token_lifetime"):
            if getattr(arguments, name) is not None:
                option = "--" + name.replace("_", "-")

                raise ValueError(f"{option} applies only with --issuer and --resource.")

        return None

    if arguments.max_token_lifetime is not None and arguments.max_token_lifetime <= 0:
        raise ValueError(
            "--max-token-lifetime must be a positive number of seconds; "
            f"got {arguments.max_token_lifetime}."
        )

    try:
        settings = AuthorizationSettings(
            issuer=arguments.issuer,
            resource=arguments.resource,
            jwks_url=arguments.jwks_url,
            algorithms=tuple(arguments.algorithm or DEFAULT_ALGORITHMS),
            max_lifetime_seconds=arguments.max_token_lifetime,
        )
    except ValidationError as exc:
        raise ValueError(
            "; ".join(str(error["msg"]).removeprefix("Value error, ") for error in exc.errors())
        ) from exc

    if urlsplit(settings.resource).path != MCP_PATH:
        raise ValueError(
            f"--resource must name the path {MCP_PATH}, where the server answers; "
            f"got {settings.resource}."
        )

    return settings


def usage_problem(
    arguments: argparse.Namespace,
) -> str | None:
    """Return why a `serve` command line cannot be used, or `None` if it can."""

    if arguments.transport == STDIO_TRANSPORT:
        given = [
            "--" + name.replace("_", "-")
            for name in HTTP_OPTIONS
            if getattr(arguments, name) is not None
        ]

        if given:
            return ", ".join(given) + " apply only with --transport http."

        return None

    try:
        authorization = authorization_settings(arguments)
        require_protection(arguments.host or DEFAULT_HOST, authorization)
    except (ValueError, UnprotectedBindError) as exc:
        return str(exc)

    if arguments.port is not None and not 0 <= arguments.port <= 65535:
        return f"--port must be between 0 and 65535; got {arguments.port}."

    return None


def exposure_path(
    argument: Path | None,
    environment: Mapping[str, str],
) -> Path | None:
    """Return the exposure document's path: the argument's, or else the environment's."""

    if argument is not None:
        return argument

    named = environment.get(EXPOSURE_ENVIRONMENT_VARIABLE, "")

    return Path(named) if named else None


def prepare_service(
    path: Path,
    configuration: CliRuntimeConfiguration,
    telemetry: Telemetry,
) -> ToolService:
    """Return the tool service for one exposure document, ready to serve.

    Raises:
        ExposureDocumentError: The document cannot be read, is not valid, or
            lists a workflow that is not active in production.
        DatabaseUnavailableError: The database cannot be used here.
        DatabaseSchemaError: The database's schema is not this Azathoth's.
        ContentStoreError: The configured content store cannot be used.
        BedrockUnavailableError: Bedrock is on, without its extra.
        BedrockConfigurationError: Bedrock is on, and misconfigured.
        ModelDiscoveryError: A provider's models cannot be discovered.
    """

    stores = repositories(configuration)
    exposure = load_exposure(path)

    check_exposure(exposure, stores.production_states)

    service = ToolService(
        catalog=ToolCatalog(exposure, stores.production_states),
        repositories=stores,
        load_runtime=lambda: load_runtime(configuration),
        telemetry=telemetry,
    )
    service.preload()

    return service


async def serve_stdio(
    server: Server[object],
) -> None:
    """Serve one client over this process's standard input and output, until it closes."""

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Run the `azathoth-mcp` command.

    It exits with status 0 when its stdio client closes the connection or
    its HTTP server shuts down, 1 when it cannot start, 2 for a command line
    it cannot use, 130 when interrupted, and 143 when terminated.
    """

    use_utf8_streams(sys.stderr)

    arguments = build_parser().parse_args(argv)
    path = exposure_path(arguments.exposure, os.environ)

    if path is None:
        print(NO_EXPOSURE_MESSAGE, file=sys.stderr)

        return 2

    problem = usage_problem(arguments)

    if problem is not None:
        print(problem, file=sys.stderr)

        return 2

    try:
        with terminating_on_sigterm():
            return run_traced(lambda telemetry: _serve(path, arguments, telemetry))
    except KeyboardInterrupt:
        print(INTERRUPTED_MESSAGE, file=sys.stderr)

        return INTERRUPTED_STATUS
    except CommandTerminated:
        print(TERMINATED_MESSAGE, file=sys.stderr)

        return TERMINATED_STATUS
    finally:
        close_postgres_databases()


def http_application(
    service: ToolService,
    authorization: AuthorizationSettings | None,
    *,
    allowed_hosts: Sequence[str] = (),
    allowed_origins: Sequence[str] = (),
) -> Starlette:
    """Return the ASGI application serving one service over HTTP.

    With authorization, it verifies tokens against the provider's published
    keys, found in its metadata unless `jwks_url` names them.

    Raises:
        AuthorizationConfigurationError: The provider's keys cannot be found.
    """

    verifier = None

    if authorization is not None:
        jwks_url = authorization.jwks_url or discover_jwks_url(authorization.issuer)
        verifier = JwtTokenVerifier(authorization, PublishedKeys(jwks_url))

    return http_app(
        build_server(service, caller_of=lambda: http_caller(get_access_token())),
        service.catalog,
        authorization=authorization,
        verifier=verifier,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


async def serve_http(
    application: Starlette,
    *,
    host: str,
    port: int,
) -> None:
    """Serve one application over HTTP until the process is stopped."""

    server = uvicorn.Server(
        uvicorn.Config(application, host=host, port=port, log_level="info", lifespan="on")
    )

    await server.serve()


def _serve(
    path: Path,
    arguments: argparse.Namespace,
    telemetry: Telemetry,
) -> int:
    """Prepare the service and serve it, or report why it cannot start."""

    try:
        configuration = CliRuntimeConfiguration.from_environment()
        service = prepare_service(path, configuration, telemetry)

        if arguments.transport == HTTP_TRANSPORT:
            application = http_application(
                service,
                authorization_settings(arguments),
                allowed_hosts=arguments.allowed_host or (),
                allowed_origins=arguments.allowed_origin or (),
            )
    except STARTUP_ERRORS as exc:
        print(str(exc), file=sys.stderr)

        return 1

    if arguments.transport == HTTP_TRANSPORT:
        asyncio.run(
            serve_http(
                application,
                host=arguments.host or DEFAULT_HOST,
                port=arguments.port if arguments.port is not None else DEFAULT_PORT,
            )
        )

        return 0

    asyncio.run(serve_stdio(build_server(service, caller_of=lambda: STDIO_CALLER)))

    return 0


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "EXPOSURE_ENVIRONMENT_VARIABLE",
    "HTTP_OPTIONS",
    "HTTP_TRANSPORT",
    "NO_EXPOSURE_MESSAGE",
    "PROGRAM",
    "STARTUP_ERRORS",
    "STDIO_TRANSPORT",
    "TRANSPORTS",
    "authorization_settings",
    "build_parser",
    "exposure_path",
    "http_application",
    "main",
    "prepare_service",
    "serve_http",
    "serve_stdio",
    "usage_problem",
]

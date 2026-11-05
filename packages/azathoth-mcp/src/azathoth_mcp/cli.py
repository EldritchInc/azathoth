"""The `azathoth-mcp` command (ADR 0111).

`azathoth-mcp serve` reads the same environment as the `azathoth` CLI, for
its database and its models' credentials, and the exposure document that
`--exposure` or `AZATHOTH_MCP_EXPOSURE` names. Before it serves anything it
checks that every exposed workflow is active in production, and composes
its runtime, so a document, a database or a provider that cannot be used
stops it with one line on stderr and status 1, before any client connects.

Over stdio, standard output carries the protocol and nothing else; every
message the command writes goes to standard error.
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

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
from azathoth_mcp.catalog import ToolCatalog, check_exposure
from azathoth_mcp.exposure import ExposureDocumentError, load_exposure
from azathoth_mcp.server import build_server
from azathoth_mcp.service import ToolService

PROGRAM = "azathoth-mcp"

EXPOSURE_ENVIRONMENT_VARIABLE = "AZATHOTH_MCP_EXPOSURE"

STDIO_TRANSPORT = "stdio"

TRANSPORTS = (STDIO_TRANSPORT,)

NO_EXPOSURE_MESSAGE = (
    f"Name the exposure document to serve with --exposure or {EXPOSURE_ENVIRONMENT_VARIABLE}."
)

STARTUP_ERRORS = (
    ExposureDocumentError,
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

    return parser


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

    It exits with status 0 when the client closes the connection, 1 when it
    cannot start, 2 for a command line it cannot read, 130 when interrupted,
    and 143 when terminated.
    """

    use_utf8_streams(sys.stderr)

    arguments = build_parser().parse_args(argv)
    path = exposure_path(arguments.exposure, os.environ)

    if path is None:
        print(NO_EXPOSURE_MESSAGE, file=sys.stderr)

        return 2

    try:
        with terminating_on_sigterm():
            return run_traced(lambda telemetry: _serve(path, telemetry))
    except KeyboardInterrupt:
        print(INTERRUPTED_MESSAGE, file=sys.stderr)

        return INTERRUPTED_STATUS
    except CommandTerminated:
        print(TERMINATED_MESSAGE, file=sys.stderr)

        return TERMINATED_STATUS
    finally:
        close_postgres_databases()


def _serve(
    path: Path,
    telemetry: Telemetry,
) -> int:
    """Prepare the service and serve it over stdio, or report why it cannot start."""

    try:
        configuration = CliRuntimeConfiguration.from_environment()
        service = prepare_service(path, configuration, telemetry)
    except STARTUP_ERRORS as exc:
        print(str(exc), file=sys.stderr)

        return 1

    asyncio.run(serve_stdio(build_server(service, caller_of=lambda: STDIO_CALLER)))

    return 0


__all__ = [
    "EXPOSURE_ENVIRONMENT_VARIABLE",
    "NO_EXPOSURE_MESSAGE",
    "PROGRAM",
    "STARTUP_ERRORS",
    "STDIO_TRANSPORT",
    "TRANSPORTS",
    "build_parser",
    "exposure_path",
    "main",
    "prepare_service",
    "serve_stdio",
]

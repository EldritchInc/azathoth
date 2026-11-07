"""Write the tool document of a tool an MCP server serves (ADR 0119).

`azathoth tool from-mcp` lists one server's tools, finds the one named, and
prints its tool document with the implementation pinned to the schemas the
server serves now. Nothing is stored: the operator reads the document and
imports it as any other.
"""

import asyncio
import sys

from pydantic import ValidationError

from azathoth.tools import (
    McpCredentials,
    McpServer,
    ToolExecutionError,
    encode_tool_document,
)
from azathoth.tools.mcp_document import mcp_tool_document, unpinned_implementation
from azathoth.tools.mcp_execution import McpConnector, McpToolExecutor

LISTING_TIMEOUT_SECONDS = 30.0
"""How long a server is given to list its tools when no timeout is named."""

SERVER_NAMED_TWICE_MESSAGE = "Name the MCP server with --url or with a command after --, not both."

SERVER_NOT_NAMED_MESSAGE = "Name the MCP server with --url, or with a command after --."


def tool_from_mcp(
    *,
    tool: str,
    url: str | None = None,
    command: tuple[str, ...] = (),
    authorization: str | None = None,
    grants: tuple[str, ...] = (),
    timeout_seconds: float | None = None,
    connect: McpConnector | None = None,
) -> int:
    """Print the tool document of one tool an MCP server serves, pinned as it is served now.

    The implementation keeps the timeout named, if any; listing the tools is
    given that timeout, or 30 seconds.
    """

    if url is not None and command:
        print(SERVER_NAMED_TWICE_MESSAGE, file=sys.stderr)

        return 1

    if url is None and not command:
        print(SERVER_NOT_NAMED_MESSAGE, file=sys.stderr)

        return 1

    try:
        server = McpServer(url=url) if url is not None else McpServer(command=command)
        unpinned = unpinned_implementation(
            server=server,
            tool=tool,
            credentials=McpCredentials(authorization=authorization),
            environment=grants,
            timeout_seconds=timeout_seconds,
        )
    except ValidationError as exc:
        print(_first_reason(exc), file=sys.stderr)

        return 1

    listing = unpinned.model_copy(
        update={
            "timeout_seconds": (
                timeout_seconds if timeout_seconds is not None else LISTING_TIMEOUT_SECONDS
            )
        }
    )

    try:
        listed = asyncio.run(McpToolExecutor(connect=connect).served_tool(listing))
    except ToolExecutionError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    if listed is None:
        print(f"MCP server {server.describe()} serves no tool named {tool!r}.", file=sys.stderr)

        return 1

    print(encode_tool_document(mcp_tool_document(unpinned, listed)))

    return 0


def _first_reason(
    error: ValidationError,
) -> str:
    """Return the first reason a model was refused for, as its validator wrote it."""

    first = error.errors()[0]
    message = str(first["msg"]).removeprefix("Value error, ")
    location = ".".join(str(part) for part in first["loc"])

    return message if first["type"] == "value_error" or not location else f"{location}: {message}"


__all__ = [
    "LISTING_TIMEOUT_SECONDS",
    "SERVER_NAMED_TWICE_MESSAGE",
    "SERVER_NOT_NAMED_MESSAGE",
    "tool_from_mcp",
]

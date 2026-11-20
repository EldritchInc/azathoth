"""Making a tool's document from a tool an MCP server serves (ADRs 0119 and 0133).

The server is asked for its tools, and the one named becomes a tool
document, its implementation pinned to the schemas the server serves now.
Nothing is kept: importing the document is `tools.import_document`, so a
person sees it before anything is.
"""

import asyncio
from typing import Final

from pydantic import ValidationError

from azathoth.api.errors import InvalidArgumentError, McpUnavailableError, NotFoundError
from azathoth.tools import McpCredentials, McpServer, ToolDocument, ToolExecutionError
from azathoth.tools.mcp_document import mcp_tool_document, unpinned_implementation
from azathoth.tools.mcp_execution import McpConnector, McpToolExecutor

LISTING_TIMEOUT_SECONDS: Final = 30.0
"""How long a server is given to list its tools when no timeout is named."""

SERVER_NAMED_TWICE_MESSAGE: Final = "Name the MCP server by its URL or by a command, not both."

SERVER_NOT_NAMED_MESSAGE: Final = "Name the MCP server by its URL or by a command."


def first_reason(
    error: ValidationError,
) -> str:
    """Return the first reason a model was refused for, as its validator wrote it."""

    first = error.errors()[0]
    message = str(first["msg"]).removeprefix("Value error, ")
    location = ".".join(str(part) for part in first["loc"])

    return message if first["type"] == "value_error" or not location else f"{location}: {message}"


def mcp_document(
    *,
    tool: str,
    url: str | None,
    command: tuple[str, ...],
    authorization: str | None,
    grants: tuple[str, ...],
    timeout_seconds: float | None,
    connect: McpConnector | None,
) -> ToolDocument:
    """Return the tool document of one tool an MCP server serves, pinned as it is served now.

    The implementation keeps the timeout named, if any; listing the tools is
    given that timeout, or 30 seconds.

    Raises:
        InvalidArgumentError: The server is named both ways or neither, or
            the implementation could not be declared.
        NotFoundError: The server serves no tool by this name.
        McpUnavailableError: The server could not be reached or listed, or
            an authorization variable it needs is not set.
    """

    if url is not None and command:
        raise InvalidArgumentError(SERVER_NAMED_TWICE_MESSAGE)

    if url is None and not command:
        raise InvalidArgumentError(SERVER_NOT_NAMED_MESSAGE)

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
        raise InvalidArgumentError(first_reason(exc)) from exc

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
        raise McpUnavailableError(str(exc)) from exc

    if listed is None:
        raise NotFoundError(f"MCP server {server.describe()} serves no tool named {tool!r}.")

    return mcp_tool_document(unpinned, listed)


__all__ = [
    "LISTING_TIMEOUT_SECONDS",
    "SERVER_NAMED_TWICE_MESSAGE",
    "SERVER_NOT_NAMED_MESSAGE",
    "first_reason",
    "mcp_document",
]

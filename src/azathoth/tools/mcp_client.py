"""The MCP SDK's side of calling a tool an MCP server serves (ADR 0119).

This is the only module that imports the SDK, and it is imported only when
an MCP implementation is executed, so the `mcp` extra is needed only by
those who call MCP tools.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
import mcp_types as types
from mcp import Client, Implementation, StdioServerParameters
from mcp.client import Transport
from mcp.client.streamable_http import streamable_http_client

from azathoth import __version__
from azathoth.tools.mcp_binding import mcp_schema_digest
from azathoth.tools.mcp_execution import (
    McpCallResult,
    McpConnection,
    McpContentBlock,
    McpListedTool,
    PinnedCall,
)

CLIENT_NAME = "azathoth"
"""The name Azathoth gives itself to the servers it calls."""

HTTP_TIMEOUT = httpx2.Timeout(30.0, read=300.0)
"""The SDK's own HTTP timeouts: a server may hold a response stream open for a while."""


def server_target(
    connection: McpConnection,
) -> Any:
    """Return what the SDK's client connects to: a stdio server's parameters, or an HTTP transport.

    A stdio server is started with exactly the connection's environment. An
    HTTP server is sent the connection's headers on every request.
    """

    command = connection.binding.server.command

    if command is not None:
        return StdioServerParameters(
            command=command[0],
            args=list(command[1:]),
            env=dict(connection.environment),
        )

    return _http_transport(str(connection.binding.server.url), dict(connection.headers))


def _http_transport(
    url: str,
    headers: dict[str, str],
) -> Transport:
    """Return the transport of an HTTP server over streamable HTTP, sending some headers."""

    return _http_streams(url, headers)


@asynccontextmanager
async def _http_streams(
    url: str,
    headers: dict[str, str],
) -> AsyncIterator[Any]:
    """Yield the streams of an HTTP server, closing the HTTP client this call opened."""

    async with (
        httpx2.AsyncClient(headers=headers, timeout=HTTP_TIMEOUT) as http_client,
        streamable_http_client(url, http_client=http_client) as streams,
    ):
        yield streams


async def call_pinned(
    target: Any,
    *,
    tool: str,
    schema_digest: str,
    arguments: dict[str, Any],
) -> PinnedCall:
    """List a server's tools, and call one only while it matches its pinned schemas.

    Nothing is raised for a tool that is missing or has drifted: the call
    reports what it found, so the executor says why, outside the client's
    task group.
    """

    async with Client(
        target, client_info=Implementation(name=CLIENT_NAME, version=__version__)
    ) as (client):
        listed = await _listed(client, tool)

        if listed is None:
            return PinnedCall(served_digest=None, result=None)

        served = mcp_schema_digest(listed.input_schema, listed.output_schema)

        if served != schema_digest:
            return PinnedCall(served_digest=served, result=None)

        result = await client.call_tool(tool, arguments)

    return PinnedCall(served_digest=served, result=_result(result))


async def listed_tool(
    target: Any,
    *,
    tool: str,
) -> McpListedTool | None:
    """Return one tool as a server lists it, reading every page, if it lists one."""

    identity = Implementation(name=CLIENT_NAME, version=__version__)

    async with Client(target, client_info=identity) as client:
        listed = await _listed(client, tool)

    if listed is None:
        return None

    return McpListedTool(
        name=listed.name,
        description=listed.description,
        input_schema=listed.input_schema,
        output_schema=listed.output_schema,
    )


async def _listed(
    client: Client,
    tool: str,
) -> types.Tool | None:
    """Return the tool a server lists under one name, reading every page, if it lists one."""

    cursor: str | None = None

    while True:
        page = await client.list_tools(cursor=cursor)

        for listed in page.tools:
            if listed.name == tool:
                return listed

        if not page.next_cursor:
            return None

        cursor = page.next_cursor


def _result(
    result: types.CallToolResult,
) -> McpCallResult:
    """Return the parts of a call's result a tool's output is made from."""

    return McpCallResult(
        is_error=bool(result.is_error),
        structured_content=result.structured_content,
        content=tuple(
            McpContentBlock(
                type=block.type,
                text=block.text if isinstance(block, types.TextContent) else None,
            )
            for block in result.content
        ),
    )


__all__ = [
    "CLIENT_NAME",
    "HTTP_TIMEOUT",
    "call_pinned",
    "listed_tool",
    "server_target",
]

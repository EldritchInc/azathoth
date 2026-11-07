"""Tests for calling a tool a real MCP server serves over streamable HTTP (ADR 0119).

The server is real: uvicorn serves the fake server on a free loopback port
in a thread, and the executor connects as a deployment would.
"""

import asyncio
import contextlib
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from azathoth.tools import (
    MCP_TOOL_RUNTIME,
    McpCredentials,
    McpServer,
    McpToolBinding,
    ToolExecutionError,
    ToolImplementation,
    mcp_schema_digest,
)
from azathoth.tools.mcp_execution import McpToolExecutor
from tests.tools.mcp_fake_server import build_fake_server, tools

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


class HeaderRecorder:
    """An ASGI endpoint recording the headers of every request it passes on."""

    def __init__(
        self,
        endpoint: StreamableHTTPASGIApp,
    ) -> None:
        self.endpoint = endpoint
        self.headers: list[dict[str, str]] = []

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Record the request's headers, then serve it."""

        self.headers.append(
            {name.decode("latin-1"): value.decode("latin-1") for name, value in scope["headers"]}
        )

        await self.endpoint(scope, receive, send)


def free_port() -> int:
    """Return a loopback port nothing listens on."""

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))

        return int(probe.getsockname()[1])


@contextlib.contextmanager
def serving(
    *,
    drift: bool = False,
) -> Iterator[tuple[str, HeaderRecorder]]:
    """Serve the fake server over HTTP in a thread, yielding its URL and its header recorder."""

    sessions = StreamableHTTPSessionManager(
        app=build_fake_server(drift=drift),
        stateless=True,
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    recorder = HeaderRecorder(StreamableHTTPASGIApp(sessions))
    application = Starlette(
        routes=[Route("/mcp", endpoint=recorder)],
        lifespan=lambda app: sessions.run(),
    )
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_config=None, lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30

    while not server.started:
        assert time.monotonic() < deadline, "The server did not start."
        time.sleep(0.02)

    try:
        yield f"http://127.0.0.1:{port}/mcp", recorder
    finally:
        server.should_exit = True
        thread.join(timeout=30)


def call(
    url: str,
    tool: str,
    inputs: dict[str, Any],
    *,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Call one of the fake server's tools over HTTP, its token in `SEARCH_TOKEN`."""

    (listed,) = (listed for listed in tools(drift=False) if listed.name == tool)

    implementation = ToolImplementation(
        id=UUID(int=1),
        tool_id=UUID(int=2),
        tool_version="1.0.0",
        runtime=MCP_TOOL_RUNTIME,
        timeout_seconds=30.0,
        mcp=McpToolBinding(
            server=McpServer(url=url),
            tool=tool,
            schema_digest=mcp_schema_digest(listed.input_schema, listed.output_schema),
            credentials=McpCredentials(authorization="SEARCH_TOKEN"),
        ),
    )

    return asyncio.run(
        McpToolExecutor(
            environ=environ if environ is not None else {"SEARCH_TOKEN": "s3cret"},
            trace_context=lambda: {"TRACEPARENT": TRACEPARENT},
        ).execute(implementation, inputs)
    )


def test_an_http_server_is_called_with_its_bearer_token_and_trace_context() -> None:
    with serving() as (url, recorder):
        assert call(url, "search", {"query": "hastur"}) == {"hits": ["hastur 1", "hastur 2"]}

    assert recorder.headers
    assert all(headers["authorization"] == "Bearer s3cret" for headers in recorder.headers)
    assert all(headers["traceparent"] == TRACEPARENT for headers in recorder.headers)


def test_an_http_server_whose_tool_drifted_is_not_called() -> None:
    with serving(drift=True) as (url, _), pytest.raises(ToolExecutionError) as raised:
        call(url, "search", {"query": "x"})

    assert "no longer matches its pinned schemas" in str(raised.value)


def test_an_http_server_that_is_not_listening_cannot_be_called() -> None:
    url = f"http://127.0.0.1:{free_port()}/mcp"

    with pytest.raises(ToolExecutionError) as raised:
        call(url, "greet", {})

    assert str(raised.value).startswith(f"MCP tool 'greet' on {url} could not be called: ")

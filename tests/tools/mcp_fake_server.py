"""A small MCP server the MCP tool tests call, in process or over stdio (ADR 0119).

Run as a script, it serves over stdio; `--drift` serves `search` under
another input schema, as a server whose tool changed would.
"""

import asyncio
import os
import sys
from typing import Any

import mcp_types as types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

SEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}

SEARCH_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"hits": {"type": "array"}},
    "required": ["hits"],
}

DRIFTED_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"q": {"type": "string"}},
    "required": ["q"],
}

ANY_OBJECT: dict[str, Any] = {"type": "object"}

PAGE_SIZE = 4
"""How many tools the server lists on one page."""

FAILURE_TEXT = "The index is down."

LOUD_FAILURE_TEXT = "a" * 600 + "b" * 10


def tools(
    *,
    drift: bool,
) -> list[types.Tool]:
    """Return every tool the server lists."""

    return [
        types.Tool(
            name="search",
            description="Search the catalog.",
            input_schema=DRIFTED_INPUT_SCHEMA if drift else SEARCH_INPUT_SCHEMA,
            output_schema=SEARCH_OUTPUT_SCHEMA,
        ),
        types.Tool(name="greet", description="Greet in two lines.", input_schema=ANY_OBJECT),
        types.Tool(name="environment", description="Name the variables.", input_schema=ANY_OBJECT),
        types.Tool(name="fail", description="Fail.", input_schema=ANY_OBJECT),
        types.Tool(
            name="fail_silently", description="Fail saying nothing.", input_schema=ANY_OBJECT
        ),
        types.Tool(name="fail_loudly", description="Fail at length.", input_schema=ANY_OBJECT),
        types.Tool(name="draw", description="Return an image.", input_schema=ANY_OBJECT),
        types.Tool(name="sleep", description="Sleep a while.", input_schema=ANY_OBJECT),
    ]


def text(
    *lines: str,
    is_error: bool = False,
) -> types.CallToolResult:
    """Return a result of some text blocks."""

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=line) for line in lines],
        is_error=is_error,
    )


async def answer(
    name: str,
    arguments: dict[str, Any],
) -> types.CallToolResult:
    """Answer one call of one tool."""

    if name == "search":
        hits = [f"{arguments['query']} {number}" for number in (1, 2)]

        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(hits))],
            structured_content={"hits": hits},
        )

    if name == "greet":
        return text("hello", "world")

    if name == "environment":
        return types.CallToolResult(
            content=[],
            structured_content={"names": sorted(os.environ), "arguments": arguments},
        )

    if name == "fail":
        return text(FAILURE_TEXT, is_error=True)

    if name == "fail_loudly":
        return text(LOUD_FAILURE_TEXT, is_error=True)

    if name == "fail_silently":
        return types.CallToolResult(content=[], is_error=True)

    if name == "draw":
        return types.CallToolResult(
            content=[types.ImageContent(type="image", data="aGk=", mime_type="image/png")]
        )

    await asyncio.sleep(30)

    return text("awake")


def build_fake_server(
    *,
    drift: bool = False,
) -> Server[Any]:
    """Return the fake server, its search tool drifted or not."""

    async def list_tools(
        context: ServerRequestContext[Any],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        #
        # Tools are listed a page at a time, so a client must read every page.
        #
        start = int(params.cursor) if params is not None and params.cursor else 0
        listed = tools(drift=drift)
        end = start + PAGE_SIZE

        return types.ListToolsResult(
            tools=listed[start:end],
            next_cursor=str(end) if end < len(listed) else None,
        )

    async def call_tool(
        context: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        return await answer(params.name, dict(params.arguments or {}))

    return Server("fake-search", on_list_tools=list_tools, on_call_tool=call_tool)


async def serve_stdio(
    *,
    drift: bool,
) -> None:
    """Serve the fake server over stdio until the client goes away."""

    server = build_fake_server(drift=drift)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(serve_stdio(drift="--drift" in sys.argv[1:]))

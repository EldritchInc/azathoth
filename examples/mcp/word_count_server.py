"""An MCP server serving one tool, `count_words`, over stdio.

Azathoth's guide to calling MCP tools (docs/mcp-tools.md) writes the tool's
document from this server and runs a workflow step that calls it. It needs
only the MCP SDK, which `azathoth-ai[mcp]` installs.
"""

import asyncio
from typing import Any

import mcp_types as types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

COUNT_WORDS = types.Tool(
    name="count_words",
    description="Count the whitespace-delimited words in a piece of text.",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {"count": {"type": "integer"}},
        "required": ["count"],
    },
)


async def list_tools(
    context: ServerRequestContext[Any],
    params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    """List the one tool."""

    return types.ListToolsResult(tools=[COUNT_WORDS])


async def call_tool(
    context: ServerRequestContext[Any],
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    """Count the words of the text, or say what is wrong with the call."""

    arguments = dict(params.arguments or {})
    text = arguments.get("text")

    if params.name != COUNT_WORDS.name or not isinstance(text, str):
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="count_words takes one string, text.")],
            is_error=True,
        )

    count = len(text.split())

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=str(count))],
        structured_content={"count": count},
    )


def build_server() -> Server[Any]:
    """Return the server."""

    return Server("word-count", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    """Serve over stdio until the client goes away."""

    server = build_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

"""The MCP server: the tool service behind the protocol's `tools/list` and `tools/call` (ADR 0111).

The server offers only tools. Each call is answered with a result the
model can read: an invocation's outcome, an invocation's evidence, or, for a
call that is refused, the reason. A refusal is a tool result marked as an
error, never a protocol error, so the model sees why and can correct the
call. An unexpected failure is logged on the server, and the client is
told only that it happened.

A caller sees only the tools its token allows, and the same rules decide
every call (`azathoth_mcp.access`).
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import mcp_types as types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from pydantic import JsonValue

from azathoth_mcp import __version__
from azathoth_mcp.access import READ_ALL_SCOPE, READ_SCOPE, McpCaller, ToolAccessError, invoke_scope
from azathoth_mcp.catalog import CatalogTool, ToolUnavailableError, UnknownToolError
from azathoth_mcp.exposure import GET_INVOCATION_TOOL
from azathoth_mcp.service import InvocationNotFoundError, ToolArgumentsError, ToolService

SERVER_NAME = "azathoth"

UNEXPECTED_FAILURE_MESSAGE = (
    "The call failed unexpectedly on the server. Its log has the details; "
    "the invocation, if one was recorded, can be read with get_invocation."
)
"""What a client is told of a failure that is not a refusal."""

SERVER_INSTRUCTIONS = (
    "Each tool runs one promoted Azathoth workflow and returns its result with the "
    "invocation's ID. Pass an idempotency_key to make a call safe to repeat. "
    "Read an invocation's evidence with get_invocation."
)

REFUSALS = (
    UnknownToolError,
    ToolAccessError,
    ToolArgumentsError,
    ToolUnavailableError,
    InvocationNotFoundError,
)
"""The errors a call is refused with, each with a message written for the model."""

WORKFLOW_TOOL_ANNOTATIONS = types.ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)
"""A workflow's tool runs models and tools; only a repeated key makes it idempotent."""

GET_INVOCATION_ANNOTATIONS = types.ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

logger = logging.getLogger(__name__)

CallerOf = Callable[[], McpCaller]
"""Return the caller of the request being handled."""


def visible_tools(
    service: ToolService,
    caller: McpCaller,
) -> tuple[CatalogTool, ...]:
    """Return the tools one caller may call, in catalog order."""

    return tuple(tool for tool in service.catalog.tools() if _may_call(caller, tool))


def mcp_tool(
    tool: CatalogTool,
) -> types.Tool:
    """Return one catalog tool as the protocol lists it."""

    return types.Tool(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        annotations=(
            WORKFLOW_TOOL_ANNOTATIONS
            if tool.workflow_id is not None
            else GET_INVOCATION_ANNOTATIONS
        ),
    )


def structured_result(
    content: dict[str, JsonValue],
    *,
    is_error: bool,
) -> types.CallToolResult:
    """Return a tool result carrying structured content, and the same as JSON text."""

    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=json.dumps(content, ensure_ascii=False)),
        ],
        structured_content=content,
        is_error=is_error,
    )


def refusal_result(
    error: Exception,
) -> types.CallToolResult:
    """Return the tool result of a refused call: its reason, as an error."""

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=str(error))],
        is_error=True,
    )


def build_server(
    service: ToolService,
    *,
    caller_of: CallerOf,
) -> Server[Any]:
    """Return a server offering one service's tools to the caller of each request."""

    async def list_tools(
        context: ServerRequestContext[Any],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[mcp_tool(tool) for tool in visible_tools(service, caller_of())],
        )

    async def call_tool(
        context: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        caller = caller_of()
        arguments: dict[str, JsonValue] = dict(params.arguments or {})

        try:
            if params.name == GET_INVOCATION_TOOL:
                evidence = service.get_invocation(arguments, caller=caller)

                return structured_result(evidence.model_dump(mode="json"), is_error=False)

            outcome = await service.invoke(
                params.name,
                arguments,
                caller=caller,
                report_progress=context.session.report_progress,
            )
        except REFUSALS as exc:
            return refusal_result(exc)
        except Exception:
            #
            # Anything else is the server's failure, not the caller's: it is
            # logged here in full, and the client is told only that it
            # happened, so nothing of the server's state reaches it.
            #
            logger.exception('A call of "%s" failed unexpectedly.', params.name)

            return refusal_result(RuntimeError(UNEXPECTED_FAILURE_MESSAGE))

        return structured_result(outcome.structured_content(), is_error=outcome.is_error)

    return Server(
        SERVER_NAME,
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def _may_call(
    caller: McpCaller,
    tool: CatalogTool,
) -> bool:
    """Report whether one caller's token allows calling one tool."""

    if caller.scopes is None:
        return True

    if tool.workflow_id is not None:
        return invoke_scope(tool.name) in caller.scopes

    return bool({READ_SCOPE, READ_ALL_SCOPE} & caller.scopes)


__all__ = [
    "GET_INVOCATION_ANNOTATIONS",
    "REFUSALS",
    "SERVER_INSTRUCTIONS",
    "SERVER_NAME",
    "UNEXPECTED_FAILURE_MESSAGE",
    "WORKFLOW_TOOL_ANNOTATIONS",
    "CallerOf",
    "build_server",
    "mcp_tool",
    "refusal_result",
    "structured_result",
    "visible_tools",
]

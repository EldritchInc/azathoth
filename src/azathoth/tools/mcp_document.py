"""The tool document of a tool an MCP server serves, pinned as it is listed now (ADR 0119).

The document is written, never stored: an operator reads it, and imports it
as any tool document is imported. Its identifiers are derived from the
server and the tool, so writing it again for the same tool names the same
tool, and a tool whose schemas drifted shows as a changed document.
"""

from uuid import UUID, uuid5

from pydantic import JsonValue

from azathoth.tools.definition import ToolDefinition, ToolInputSchema, ToolOutputSchema
from azathoth.tools.document import ToolDocument
from azathoth.tools.implementation import ToolImplementation
from azathoth.tools.mcp_binding import (
    MCP_TOOL_RUNTIME,
    McpCredentials,
    McpServer,
    McpToolBinding,
    mcp_schema_digest,
)
from azathoth.tools.mcp_execution import TEXT_OUTPUT, McpListedTool

MCP_DOCUMENT_NAMESPACE = UUID("a0119000-0000-4000-8000-000000000000")
"""The namespace an MCP tool document's identifiers are derived in."""

MCP_TOOL_VERSION = "1.0.0"
"""The version a written MCP tool document gives its tool and implementation."""

MCP_TEXT_OUTPUT_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {TEXT_OUTPUT: {"type": "string"}},
    "required": [TEXT_OUTPUT],
    "additionalProperties": False,
}
"""The output of a tool that names no output schema: its text."""

UNPINNED_DIGEST = "0" * 64
"""The digest a binding is written with before its tool has been listed."""


def unpinned_implementation(
    *,
    server: McpServer,
    tool: str,
    credentials: McpCredentials,
    environment: tuple[str, ...] = (),
    timeout_seconds: float | None = None,
) -> ToolImplementation:
    """Return the implementation a binding would be before it is pinned, to list its tool with.

    Raises:
        ValueError: The binding is not one an implementation may declare.
    """

    return ToolImplementation(
        tool_id=MCP_DOCUMENT_NAMESPACE,
        tool_version=MCP_TOOL_VERSION,
        runtime=MCP_TOOL_RUNTIME,
        timeout_seconds=timeout_seconds,
        environment=environment,
        mcp=McpToolBinding(
            server=server,
            tool=tool,
            schema_digest=UNPINNED_DIGEST,
            credentials=credentials,
        ),
    )


def mcp_tool_document(
    unpinned: ToolImplementation,
    listed: McpListedTool,
) -> ToolDocument:
    """Return the tool document of a listed tool, its implementation pinned to its schemas.

    The definition takes the tool's name, its description and its schemas;
    a tool that names no output schema is given the schema of its text. The
    implementation keeps the unpinned one's server, credentials, grants and
    timeout.
    """

    binding = unpinned.mcp

    if binding is None:
        raise ValueError("Only an MCP implementation can be pinned.")

    server = binding.server.describe()
    digest = mcp_schema_digest(listed.input_schema, listed.output_schema)
    tool_id = uuid5(MCP_DOCUMENT_NAMESPACE, f"tool\n{server}\n{listed.name}")

    return ToolDocument(
        definition=ToolDefinition(
            id=tool_id,
            name=listed.name,
            description=(
                listed.description
                if listed.description and listed.description.strip()
                else f"Call the MCP tool {listed.name!r} on {server}."
            ),
            version=MCP_TOOL_VERSION,
            input_schema=ToolInputSchema(json_schema=listed.input_schema),
            output_schema=ToolOutputSchema(
                json_schema=(
                    listed.output_schema
                    if listed.output_schema is not None
                    else MCP_TEXT_OUTPUT_SCHEMA
                )
            ),
        ),
        implementations=(
            unpinned.model_copy(
                update={
                    "id": uuid5(
                        MCP_DOCUMENT_NAMESPACE, f"implementation\n{server}\n{listed.name}\n{digest}"
                    ),
                    "tool_id": tool_id,
                    "mcp": binding.model_copy(update={"schema_digest": digest}),
                }
            ),
        ),
    )


__all__ = [
    "MCP_DOCUMENT_NAMESPACE",
    "MCP_TEXT_OUTPUT_SCHEMA",
    "MCP_TOOL_VERSION",
    "UNPINNED_DIGEST",
    "mcp_tool_document",
    "unpinned_implementation",
]

"""Execution of MCP tool implementations: one call of a tool an MCP server serves (ADR 0119).

Each call opens its own connection, lists the server's tools, checks the
bound tool against its pinned schemas, calls it, and closes the connection.
The SDK is imported only here, on the first call, through
`azathoth.tools.mcp_client`, so the `mcp` extra is needed only by those who
call MCP tools.
"""

import asyncio
import importlib
import os
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, JsonValue

from azathoth.telemetry.api import active_telemetry
from azathoth.tools.environment import process_tool_environment
from azathoth.tools.exceptions import ToolExecutionError, UnsupportedToolRuntimeError
from azathoth.tools.implementation import (
    LINEAGE_ENVIRONMENT_VARIABLE,
    PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,
    TRACEPARENT_ENVIRONMENT_VARIABLE,
    TRACESTATE_ENVIRONMENT_VARIABLE,
    ToolImplementation,
)
from azathoth.tools.mcp_binding import MCP_TOOL_RUNTIME, McpToolBinding

MCP_UNAVAILABLE_MESSAGE = (
    "MCP tools need the mcp package, which is not installed; install azathoth-ai[mcp]."
)
"""Why an MCP implementation cannot run where the SDK is not installed."""

MCP_FAILURE_TAIL_CHARACTERS = 500
"""The most trailing characters of a server's message quoted when a call fails."""

TEXT_OUTPUT = "text"
"""The output holding a tool's text, when it returns no structured content."""

AUTHORIZATION_HEADER = "Authorization"

TRACE_HEADERS = {
    TRACEPARENT_ENVIRONMENT_VARIABLE: "traceparent",
    TRACESTATE_ENVIRONMENT_VARIABLE: "tracestate",
}
"""The W3C header each trace context variable is sent to an HTTP server as."""


class McpUnavailableError(ToolExecutionError):
    """Raised when an MCP implementation runs where the SDK is not installed."""

    def __init__(self) -> None:
        super().__init__(MCP_UNAVAILABLE_MESSAGE)


class McpConnection(BaseModel):
    """What one call connects with.

    That is the binding, and a stdio server's environment or an HTTP
    server's headers.
    """

    model_config = ConfigDict(frozen=True)

    binding: McpToolBinding
    environment: dict[str, str] = {}
    headers: dict[str, str] = {}


class McpContentBlock(BaseModel):
    """One content block of a call's result: its kind, and its text when it is text."""

    model_config = ConfigDict(frozen=True)

    type: str
    text: str | None = None


class McpCallResult(BaseModel):
    """The parts of a call's result a tool's output is made from."""

    model_config = ConfigDict(frozen=True)

    is_error: bool
    structured_content: dict[str, Any] | None = None
    content: tuple[McpContentBlock, ...] = ()


class McpListedTool(BaseModel):
    """One tool as a server lists it: its name, description and schemas."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None


class PinnedCall(BaseModel):
    """What a call found.

    That is the served tool's schema digest, if it is served, and its result,
    if it was called.
    """

    model_config = ConfigDict(frozen=True)

    served_digest: str | None
    result: McpCallResult | None


McpConnector = Callable[[McpConnection], Any]
"""Return what the SDK's client connects to for one connection."""


class McpToolExecutor:
    """Execute MCP implementations by calling the tool their binding names.

    A stdio server is started with the environment a process tool would be
    given, its own grants and the base variables (ADR 0099), and the step's
    trace context; it is not Azathoth, so it receives no lineage. An HTTP
    server is sent the bearer token its binding's authorization variable
    holds, and the step's trace context as `traceparent` and `tracestate`.
    A credential's value is never recorded or quoted.
    """

    def __init__(
        self,
        *,
        connect: McpConnector | None = None,
        environ: Mapping[str, str] | None = None,
        trace_context: Callable[[], Mapping[str, str]] | None = None,
    ) -> None:
        self._connect = connect
        self._environ = environ
        self._trace_context = trace_context

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Call the bound tool with the inputs as its arguments, and return its output.

        The output is the tool's structured content, or else its text as
        `text`.

        Raises:
            UnsupportedToolRuntimeError: The implementation is not an MCP
                implementation.
            McpUnavailableError: The SDK is not installed.
            ToolExecutionError: An authorization variable is not set; the
                server could not be reached, does not serve the tool, or
                serves it under other schemas; the call timed out or failed;
                or the tool returned content a tool output cannot hold.
        """

        binding = self._require_binding(implementation)
        connection = self._connection(implementation, binding)
        client = _client_module()
        connect = self._connect if self._connect is not None else client.server_target
        name = _named(binding)

        try:
            async with asyncio.timeout(implementation.timeout_seconds):
                called = await client.call_pinned(
                    connect(connection),
                    tool=binding.tool,
                    schema_digest=binding.schema_digest,
                    arguments=inputs,
                )
        except TimeoutError as exc:
            raise ToolExecutionError(
                f"{name} did not answer within {implementation.timeout_seconds:g} seconds."
            ) from exc
        except Exception as exc:
            raise ToolExecutionError(f"{name} could not be called: {_tail(_reason(exc))}") from exc

        return _output(binding, called)

    async def served_tool(
        self,
        implementation: ToolImplementation,
    ) -> McpListedTool | None:
        """Return the tool an implementation's binding names as its server lists it now, if it does.

        Nothing is called and the pin is not checked: this is how a binding
        is written, and how its drift is seen.

        Raises:
            UnsupportedToolRuntimeError: The implementation is not an MCP
                implementation.
            McpUnavailableError: The SDK is not installed.
            ToolExecutionError: An authorization variable is not set, or the
                server could not be reached or did not list its tools in
                time.
        """

        binding = self._require_binding(implementation)
        connection = self._connection(implementation, binding)
        client = _client_module()
        connect = self._connect if self._connect is not None else client.server_target
        server = f"MCP server {binding.server.describe()}"

        try:
            async with asyncio.timeout(implementation.timeout_seconds):
                listed: McpListedTool | None = await client.listed_tool(
                    connect(connection), tool=binding.tool
                )
        except TimeoutError as exc:
            raise ToolExecutionError(
                f"{server} did not list its tools within "
                f"{implementation.timeout_seconds:g} seconds."
            ) from exc
        except Exception as exc:
            raise ToolExecutionError(
                f"{server} could not be listed: {_tail(_reason(exc))}"
            ) from exc

        return listed

    @staticmethod
    def _require_binding(
        implementation: ToolImplementation,
    ) -> McpToolBinding:
        """Return the binding of an MCP implementation."""

        if implementation.runtime != MCP_TOOL_RUNTIME:
            raise UnsupportedToolRuntimeError("McpToolExecutor only supports the 'mcp' runtime.")

        if implementation.mcp is None:
            raise ToolExecutionError(
                f"Tool implementation {implementation.id} does not declare an MCP binding."
            )

        return implementation.mcp

    def _connection(
        self,
        implementation: ToolImplementation,
        binding: McpToolBinding,
    ) -> McpConnection:
        """Return what one call connects with, reading credentials from the environment now."""

        context = dict(
            active_telemetry().trace_context()
            if self._trace_context is None
            else self._trace_context()
        )

        if binding.server.is_stdio:
            environment = process_tool_environment(
                implementation, self._environ, trace_context=context
            )
            environment.pop(LINEAGE_ENVIRONMENT_VARIABLE, None)
            environment.pop(PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE, None)

            return McpConnection(binding=binding, environment=environment)

        headers = {
            header: context[variable]
            for variable, header in TRACE_HEADERS.items()
            if context.get(variable)
        }
        variable = binding.credentials.authorization

        if variable is not None:
            environ = os.environ if self._environ is None else self._environ
            token = environ.get(variable)

            if not token:
                raise ToolExecutionError(
                    f"{_named(binding)} needs its authorization variable {variable}, which is "
                    "not set."
                )

            headers[AUTHORIZATION_HEADER] = f"Bearer {token}"

        return McpConnection(binding=binding, headers=headers)


def _client_module() -> Any:
    """Import the SDK's side of a call, or say which extra to install."""

    try:
        importlib.import_module("mcp")
    except ImportError as exc:
        raise McpUnavailableError() from exc

    return importlib.import_module("azathoth.tools.mcp_client")


def _named(
    binding: McpToolBinding,
) -> str:
    """Return the bound tool as messages name it: the tool, then its server."""

    return f"MCP tool {binding.tool!r} on {binding.server.describe()}"


def _output(
    binding: McpToolBinding,
    called: PinnedCall,
) -> dict[str, JsonValue]:
    """Return a call's output, or say why the tool was not called or failed."""

    name = _named(binding)

    if called.served_digest is None:
        raise ToolExecutionError(
            f"MCP server {binding.server.describe()} serves no tool named {binding.tool!r}."
        )

    if called.result is None:
        raise ToolExecutionError(
            f"{name} no longer matches its pinned schemas: pinned {binding.schema_digest}, "
            f"served {called.served_digest}."
        )

    texts = [block.text for block in called.result.content if block.text is not None]

    if called.result.is_error:
        reason = "\n".join(texts).strip() or "it gave no reason"

        raise ToolExecutionError(f"{name} failed: {_tail(reason)}")

    if called.result.structured_content is not None:
        return dict(called.result.structured_content)

    for block in called.result.content:
        if block.text is None:
            raise ToolExecutionError(
                f"{name} returned {block.type} content, which a tool's output cannot hold yet."
            )

    return {TEXT_OUTPUT: "\n".join(texts)}


def _reason(
    error: BaseException,
) -> str:
    """Return the message of an error, or of the first error a group holds."""

    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]

    return str(error) or type(error).__name__


def _tail(
    message: str,
) -> str:
    """Return the trailing characters of a server's message that a failure quotes."""

    return message[-MCP_FAILURE_TAIL_CHARACTERS:]


__all__ = [
    "AUTHORIZATION_HEADER",
    "MCP_FAILURE_TAIL_CHARACTERS",
    "MCP_UNAVAILABLE_MESSAGE",
    "TEXT_OUTPUT",
    "TRACE_HEADERS",
    "McpCallResult",
    "McpConnection",
    "McpConnector",
    "McpContentBlock",
    "McpListedTool",
    "McpToolExecutor",
    "McpUnavailableError",
    "PinnedCall",
]

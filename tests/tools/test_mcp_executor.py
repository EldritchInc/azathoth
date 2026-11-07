"""Tests for calling a tool an MCP server serves (ADR 0119)."""

import asyncio
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from mcp import StdioServerParameters
from pydantic import JsonValue

from azathoth.context import Context, ContextEvent
from azathoth.strategies import StrategyMetadata
from azathoth.tools import (
    MCP_TOOL_RUNTIME,
    PROCESS_TOOL_RUNTIME,
    McpCredentials,
    McpServer,
    McpToolBinding,
    RuntimeToolExecutor,
    ToolExecutionError,
    ToolImplementation,
    ToolStrategy,
    UnsupportedToolRuntimeError,
    default_tool_executors,
    mcp_schema_digest,
    supported_tool_runtimes,
)
from azathoth.tools.mcp_client import server_target
from azathoth.tools.mcp_execution import (
    MCP_UNAVAILABLE_MESSAGE,
    McpConnection,
    McpToolExecutor,
    McpUnavailableError,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowConstantValue,
    WorkflowContextReference,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowValueBinding,
)
from tests.tools.mcp_fake_server import (
    FAILURE_TEXT,
    LOUD_FAILURE_TEXT,
    PAGE_SIZE,
    build_fake_server,
    tools,
)

FAKE_SERVER = Path(__file__).with_name("mcp_fake_server.py")

TOOL_ID = UUID("01190000-0000-4000-8000-000000000101")

IMPLEMENTATION_ID = UUID("01190000-0000-4000-8000-000000000102")

URL = "https://mcp.example.com/mcp"

HTTP = McpServer(url=URL)

STDIO_COMMAND = (sys.executable, str(FAKE_SERVER))

TRACE = {
    "TRACEPARENT": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    "TRACESTATE": "azathoth=1",
}


def pinned(
    tool: str,
) -> str:
    """Return the digest the fake server's undrifted tool is pinned to."""

    (listed,) = (listed for listed in tools(drift=False) if listed.name == tool)

    return mcp_schema_digest(listed.input_schema, listed.output_schema)


def implementation(
    tool: str,
    *,
    server: McpServer = HTTP,
    digest: str | None = None,
    authorization: str | None = None,
    **fields: Any,
) -> ToolImplementation:
    """Return an MCP implementation calling one of the fake server's tools."""

    return ToolImplementation.model_validate(
        {
            "id": IMPLEMENTATION_ID,
            "tool_id": TOOL_ID,
            "tool_version": "1.0.0",
            "runtime": MCP_TOOL_RUNTIME,
            "mcp": McpToolBinding(
                server=server,
                tool=tool,
                schema_digest=digest if digest is not None else pinned(tool),
                credentials=McpCredentials(authorization=authorization),
            ),
            **fields,
        }
    )


class Recorder:
    """Connect every call to the fake server in process, recording each connection."""

    def __init__(
        self,
        *,
        drift: bool = False,
    ) -> None:
        self.drift = drift
        self.connections: list[McpConnection] = []

    def __call__(
        self,
        connection: McpConnection,
    ) -> Any:
        """Record the connection and return the in-process server."""

        self.connections.append(connection)

        return build_fake_server(drift=self.drift)


def executor(
    connect: Any = None,
    *,
    environ: dict[str, str] | None = None,
    trace: dict[str, str] | None = None,
) -> McpToolExecutor:
    """Return an executor over the in-process fake server, with no ambient environment."""

    return McpToolExecutor(
        connect=connect if connect is not None else Recorder(),
        environ=environ if environ is not None else {},
        trace_context=lambda: dict(trace or {}),
    )


def call(
    implementation: ToolImplementation,
    inputs: dict[str, JsonValue] | None = None,
    **options: Any,
) -> dict[str, JsonValue]:
    """Call one implementation with some inputs."""

    return asyncio.run(executor(**options).execute(implementation, inputs or {}))


def failure(
    implementation: ToolImplementation,
    inputs: dict[str, JsonValue] | None = None,
    **options: Any,
) -> str:
    """Return the message one call fails with."""

    with pytest.raises(ToolExecutionError) as raised:
        call(implementation, inputs, **options)

    return str(raised.value)


# Calls


def test_a_call_sends_the_inputs_and_returns_the_structured_content() -> None:
    assert call(implementation("search"), {"query": "shoggoth"}) == {
        "hits": ["shoggoth 1", "shoggoth 2"]
    }


def test_a_tool_without_structured_content_returns_its_text() -> None:
    assert call(implementation("greet")) == {"text": "hello\nworld"}


def test_the_inputs_are_the_arguments_exactly() -> None:
    inputs: dict[str, JsonValue] = {"ticket": {"id": 7, "tags": ["a", None]}, "limit": 3}

    assert call(implementation("environment"), inputs)["arguments"] == inputs


# Pins


def test_a_tool_whose_schemas_drifted_is_not_called() -> None:
    drifted = tools(drift=True)[0]

    assert failure(implementation("search"), {"query": "x"}, connect=Recorder(drift=True)) == (
        f"MCP tool 'search' on {URL} no longer matches its pinned schemas: pinned "
        f"{pinned('search')}, served "
        f"{mcp_schema_digest(drifted.input_schema, drifted.output_schema)}."
    )


def test_a_tool_the_server_does_not_serve_is_not_called() -> None:
    assert failure(implementation("nope", digest=pinned("greet"))) == (
        f"MCP server {URL} serves no tool named 'nope'."
    )


# Failures


def test_a_failed_call_quotes_the_servers_message() -> None:
    assert failure(implementation("fail")) == f"MCP tool 'fail' on {URL} failed: {FAILURE_TEXT}"


def test_a_failed_call_without_a_message_says_so() -> None:
    assert failure(implementation("fail_silently")) == (
        f"MCP tool 'fail_silently' on {URL} failed: it gave no reason"
    )


def test_a_long_failure_quotes_only_its_last_characters() -> None:
    assert failure(implementation("fail_loudly")) == (
        f"MCP tool 'fail_loudly' on {URL} failed: {LOUD_FAILURE_TEXT[-500:]}"
    )


def test_content_a_tool_output_cannot_hold_is_refused() -> None:
    assert failure(implementation("draw")) == (
        f"MCP tool 'draw' on {URL} returned image content, which a tool's output cannot hold yet."
    )


def test_a_call_that_outlasts_its_timeout_fails() -> None:
    assert failure(implementation("sleep", timeout_seconds=0.2)) == (
        f"MCP tool 'sleep' on {URL} did not answer within 0.2 seconds."
    )


def test_a_server_that_cannot_be_reached_says_why() -> None:
    def unreachable(
        connection: McpConnection,
    ) -> Any:
        raise ConnectionRefusedError("Connection refused")

    assert failure(implementation("greet"), connect=unreachable) == (
        f"MCP tool 'greet' on {URL} could not be called: Connection refused"
    )


def test_a_failure_inside_a_task_group_is_named_by_its_first_error() -> None:
    def grouped(
        connection: McpConnection,
    ) -> Any:
        raise ExceptionGroup("unhandled errors", [OSError("Name or service not known")])

    assert failure(implementation("greet"), connect=grouped) == (
        f"MCP tool 'greet' on {URL} could not be called: Name or service not known"
    )


def test_a_failure_without_a_message_is_named_by_its_type() -> None:
    def silent(
        connection: McpConnection,
    ) -> Any:
        raise OSError()

    assert failure(implementation("greet"), connect=silent) == (
        f"MCP tool 'greet' on {URL} could not be called: OSError"
    )


def test_only_mcp_implementations_are_executed() -> None:
    process = ToolImplementation(
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=PROCESS_TOOL_RUNTIME,
        command=("bash",),
        source="x",
    )

    with pytest.raises(UnsupportedToolRuntimeError) as raised:
        asyncio.run(executor().execute(process, {}))

    assert str(raised.value) == "McpToolExecutor only supports the 'mcp' runtime."


def test_an_implementation_without_a_binding_is_refused_by_name() -> None:
    unbound = implementation("greet").model_copy(update={"mcp": None})

    with pytest.raises(ToolExecutionError) as raised:
        asyncio.run(executor().execute(unbound, {}))

    assert str(raised.value) == (
        f"Tool implementation {IMPLEMENTATION_ID} does not declare an MCP binding."
    )


def test_without_the_sdk_the_extra_to_install_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "mcp", None)

    with pytest.raises(McpUnavailableError) as raised:
        call(implementation("greet"))

    assert (
        str(raised.value)
        == MCP_UNAVAILABLE_MESSAGE
        == ("MCP tools need the mcp package, which is not installed; install azathoth-ai[mcp].")
    )


# Credentials and trace context


def connection_of(
    implementation: ToolImplementation,
    *,
    environ: dict[str, str] | None = None,
    trace: dict[str, str] | None = None,
) -> McpConnection:
    """Call one implementation and return what it connected with."""

    recorder = Recorder()

    call(implementation, {"query": "x"}, connect=recorder, environ=environ, trace=trace)

    (connection,) = recorder.connections

    return connection


def test_an_http_server_is_sent_its_bearer_token_and_the_trace_context() -> None:
    connection = connection_of(
        implementation("search", authorization="SEARCH_TOKEN"),
        environ={"SEARCH_TOKEN": "s3cret", "OTHER": "x"},
        trace=TRACE,
    )

    assert connection.headers == {
        "traceparent": TRACE["TRACEPARENT"],
        "tracestate": "azathoth=1",
        "Authorization": "Bearer s3cret",
    }
    assert connection.environment == {}


def test_an_http_server_without_credentials_or_a_trace_is_sent_no_headers() -> None:
    assert connection_of(implementation("search")).headers == {}


def test_an_empty_trace_state_is_not_sent() -> None:
    connection = connection_of(
        implementation("search"),
        trace={"TRACEPARENT": TRACE["TRACEPARENT"], "TRACESTATE": ""},
    )

    assert connection.headers == {"traceparent": TRACE["TRACEPARENT"]}


def test_a_tool_listed_on_a_later_page_is_found() -> None:
    assert [listed.name for listed in tools(drift=False)].index("greet") < PAGE_SIZE
    assert [listed.name for listed in tools(drift=False)].index("sleep") >= PAGE_SIZE
    assert failure(implementation("sleep", timeout_seconds=0.2)).endswith(
        "did not answer within 0.2 seconds."
    )


@pytest.mark.parametrize(
    "environ",
    [pytest.param({}, id="unset"), pytest.param({"SEARCH_TOKEN": ""}, id="empty")],
)
def test_an_authorization_variable_that_is_not_set_fails_before_connecting(
    environ: dict[str, str],
) -> None:
    recorder = Recorder()

    assert failure(
        implementation("search", authorization="SEARCH_TOKEN"),
        connect=recorder,
        environ=environ,
    ) == (
        f"MCP tool 'search' on {URL} needs its authorization variable SEARCH_TOKEN, which is "
        "not set."
    )
    assert recorder.connections == []


def test_a_token_never_reaches_a_failure() -> None:
    message = failure(
        implementation("fail", authorization="SEARCH_TOKEN"),
        environ={"SEARCH_TOKEN": "s3cret"},
    )

    assert "s3cret" not in message


def test_a_stdio_server_gets_its_grants_the_base_and_the_trace_and_no_lineage() -> None:
    connection = connection_of(
        implementation(
            "search",
            server=McpServer(command=("search-server",)),
            environment=("SEARCH_*",),
            timeout_seconds=5.0,
        ),
        environ={
            "PATH": "/usr/bin",
            "SEARCH_KEY": "k",
            "SECRET": "s",
            "AZATHOTH_LINEAGE": "{}",
            "AZATHOTH_TOOL_TIMEOUT_SECONDS": "9",
        },
        trace=TRACE,
    )

    assert connection.environment == {"PATH": "/usr/bin", "SEARCH_KEY": "k", **TRACE}
    assert connection.headers == {}


def test_a_stdio_target_starts_the_command_with_exactly_its_environment() -> None:
    target = server_target(
        McpConnection(
            binding=McpToolBinding(
                server=McpServer(command=("npx", "-y", "@acme/search")),
                tool="search",
                schema_digest=pinned("search"),
            ),
            environment={"PATH": "/usr/bin"},
        )
    )

    assert isinstance(target, StdioServerParameters)
    assert (target.command, target.args, target.env) == (
        "npx",
        ["-y", "@acme/search"],
        {"PATH": "/usr/bin"},
    )


# A real stdio server


def stdio_call(
    tool: str,
    inputs: dict[str, JsonValue],
    *,
    arguments: tuple[str, ...] = (),
    environment: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    """Call the fake server started over stdio, as a deployment would."""

    return asyncio.run(
        McpToolExecutor(
            environ={"PATH": "/usr/bin:/bin", "SEARCH_KEY": "k", "SECRET": "s"},
            trace_context=dict,
        ).execute(
            implementation(
                tool,
                server=McpServer(command=(*STDIO_COMMAND, *arguments)),
                environment=environment,
                timeout_seconds=30.0,
            ),
            inputs,
        )
    )


def test_a_stdio_server_is_started_called_and_stopped() -> None:
    assert stdio_call("search", {"query": "dagon"}) == {"hits": ["dagon 1", "dagon 2"]}


def test_a_stdio_server_sees_only_the_variables_it_was_granted() -> None:
    names = stdio_call("environment", {}, environment=("SEARCH_KEY",))["names"]

    assert isinstance(names, list)
    assert "SEARCH_KEY" in names
    assert "SECRET" not in names


def test_a_stdio_server_whose_tool_drifted_is_not_called() -> None:
    with pytest.raises(ToolExecutionError) as raised:
        stdio_call("search", {"query": "x"}, arguments=("--drift",))

    assert "no longer matches its pinned schemas" in str(raised.value)


# Dispatch and steps


def test_mcp_is_a_supported_runtime_with_its_own_executor() -> None:
    assert supported_tool_runtimes() == ("mcp", "process", "python")
    assert isinstance(default_tool_executors()[MCP_TOOL_RUNTIME], McpToolExecutor)


def test_a_tool_step_binds_an_mcp_tools_inputs_as_any_tools_and_hands_on_no_lineage() -> None:
    recorder = Recorder()
    strategy = ToolStrategy(
        metadata=StrategyMetadata(
            id=TOOL_ID, name="environment", description="Echo.", version="1.0.0"
        ),
        implementation=implementation("environment", server=McpServer(command=("search-server",))),
        executor=RuntimeToolExecutor({MCP_TOOL_RUNTIME: executor(recorder)}),
    )
    candidate = WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=UUID(int=1), name="mcp step", description="Call an MCP tool.", version="1.0.0"
        ),
        steps=(
            WorkflowCandidateStep(
                id=UUID(int=2),
                strategy=strategy,
                inputs=(
                    WorkflowInputBinding(name="limit", source=WorkflowConstantValue(value=3)),
                    WorkflowInputBinding(
                        name="request",
                        source=WorkflowContextReference(
                            event_type="request.received", field_name="input"
                        ),
                    ),
                ),
                outputs=(WorkflowValueBinding(name="arguments", path=("arguments",)),),
            ),
        ),
    )

    context = Context(
        events=(
            ContextEvent(
                event_type="request.received",
                payload={"input": "ticket 7"},
                producer="request-api",
            ),
        )
    )
    run = asyncio.run(WorkflowRunner().run(candidate, context))

    (value,) = run.values_named("arguments")

    assert value.value == {"limit": 3, "request": "ticket 7"}

    execution = run.steps[0].execution

    assert execution is not None

    (tool,) = (resource for resource in execution.resources if resource.kind == "tool")

    assert tool.attributes["runtime"] == "mcp"

    (connection,) = recorder.connections

    assert "AZATHOTH_LINEAGE" not in connection.environment

"""Tests for writing the tool document of a tool an MCP server serves (ADR 0119)."""

import asyncio
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

import mcp_types as types
import pytest
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from pydantic import ValidationError

from azathoth.cli import build_parser, import_tool, tool_from_mcp
from azathoth.cli.dispatching.tools import dispatch_tool_command
from azathoth.cli.mcp_tools import (
    LISTING_TIMEOUT_SECONDS,
    SERVER_NAMED_TWICE_MESSAGE,
    SERVER_NOT_NAMED_MESSAGE,
)
from azathoth.evaluation import json_schema_validator, json_schema_violations
from azathoth.tools import (
    MCP_TOOL_RUNTIME,
    McpCredentials,
    McpServer,
    SQLiteToolRepository,
    decode_tool_document,
    mcp_schema_digest,
)
from azathoth.tools.mcp_document import (
    MCP_DOCUMENT_NAMESPACE,
    MCP_TEXT_OUTPUT_SCHEMA,
    UNPINNED_DIGEST,
    mcp_tool_document,
    unpinned_implementation,
)
from azathoth.tools.mcp_execution import McpConnection, McpListedTool, McpToolExecutor
from tests.tools.mcp_fake_server import (
    SEARCH_INPUT_SCHEMA,
    SEARCH_OUTPUT_SCHEMA,
    build_fake_server,
)

FAKE_SERVER = Path(__file__).parents[1] / "tools" / "mcp_fake_server.py"

URL = "https://mcp.example.com/mcp"

SEARCH = McpListedTool(
    name="search",
    description="Search the catalog.",
    input_schema=SEARCH_INPUT_SCHEMA,
    output_schema=SEARCH_OUTPUT_SCHEMA,
)


def unpinned(
    *,
    server: McpServer | None = None,
    **fields: Any,
) -> Any:
    """Return an unpinned implementation of a tool on the HTTP server."""

    return unpinned_implementation(
        server=server if server is not None else McpServer(url=URL),
        tool=fields.pop("tool", "search"),
        credentials=fields.pop("credentials", McpCredentials()),
        **fields,
    )


def in_process(
    connection: McpConnection,
) -> Any:
    """Connect to the fake server in process."""

    return build_fake_server()


def written(
    capsys: pytest.CaptureFixture[str],
    **options: Any,
) -> tuple[int, str, str]:
    """Write one tool's document; return the status, output and errors."""

    status = tool_from_mcp(**{"url": URL, "tool": "search", "connect": in_process, **options})
    captured = capsys.readouterr()

    return status, captured.out, captured.err


# The document


def test_a_document_takes_the_tools_name_description_and_schemas_and_pins_them() -> None:
    document = mcp_tool_document(unpinned(), SEARCH)
    (implementation,) = document.implementations

    assert (document.definition.name, document.definition.description) == (
        "search",
        "Search the catalog.",
    )
    assert document.definition.input_schema.json_schema == SEARCH_INPUT_SCHEMA
    assert document.definition.output_schema.json_schema == SEARCH_OUTPUT_SCHEMA
    assert document.test_cases == ()
    assert implementation.runtime == MCP_TOOL_RUNTIME
    assert implementation.tool_id == document.definition.id
    assert implementation.mcp is not None
    assert implementation.mcp.schema_digest == mcp_schema_digest(
        SEARCH_INPUT_SCHEMA, SEARCH_OUTPUT_SCHEMA
    )


def test_a_tool_without_an_output_schema_is_given_the_schema_of_its_text() -> None:
    document = mcp_tool_document(
        unpinned(tool="greet"),
        McpListedTool(name="greet", description="Greet.", input_schema={"type": "object"}),
    )

    assert (
        document.definition.output_schema.json_schema
        == MCP_TEXT_OUTPUT_SCHEMA
        == {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }
    )
    assert document.implementations[0].mcp is not None
    assert document.implementations[0].mcp.schema_digest == mcp_schema_digest(
        {"type": "object"}, None
    )


@pytest.mark.parametrize("description", [None, "", "   "])
def test_a_tool_without_a_description_is_described_by_its_server(
    description: str | None,
) -> None:
    listed = SEARCH.model_copy(update={"description": description})

    assert mcp_tool_document(unpinned(), listed).definition.description == (
        f"Call the MCP tool 'search' on {URL}."
    )


def test_the_implementation_keeps_the_servers_credentials_grants_and_timeout() -> None:
    http = mcp_tool_document(
        unpinned(credentials=McpCredentials(authorization="TOKEN"), timeout_seconds=20.0),
        SEARCH,
    ).implementations[0]
    stdio = mcp_tool_document(
        unpinned(server=McpServer(command=("search-server",)), environment=("SEARCH_*",)),
        SEARCH,
    ).implementations[0]

    assert http.mcp is not None
    assert http.mcp.credentials.authorization == "TOKEN"
    assert http.timeout_seconds == 20.0
    assert stdio.environment == ("SEARCH_*",)
    assert stdio.timeout_seconds is None


def test_writing_a_document_again_names_the_same_tool_and_implementation() -> None:
    first = mcp_tool_document(unpinned(), SEARCH)

    assert mcp_tool_document(unpinned(), SEARCH) == first
    assert first.definition.id != MCP_DOCUMENT_NAMESPACE


def test_a_drifted_tool_is_the_same_tool_with_another_implementation() -> None:
    first = mcp_tool_document(unpinned(), SEARCH)
    drifted = mcp_tool_document(
        unpinned(), SEARCH.model_copy(update={"input_schema": {"type": "object"}})
    )

    assert drifted.definition.id == first.definition.id
    assert drifted.implementations[0].id != first.implementations[0].id


def test_another_server_or_tool_is_another_tool() -> None:
    first = mcp_tool_document(unpinned(), SEARCH)

    assert (
        mcp_tool_document(
            unpinned(server=McpServer(url="https://other.example/mcp")), SEARCH
        ).definition.id
        != first.definition.id
    )
    assert (
        mcp_tool_document(
            unpinned(tool="lookup"), SEARCH.model_copy(update={"name": "lookup"})
        ).definition.id
        != first.definition.id
    )


def test_an_unpinned_implementation_is_written_with_a_placeholder_digest() -> None:
    implementation = unpinned()

    assert implementation.mcp is not None
    assert implementation.mcp.schema_digest == UNPINNED_DIGEST == "0" * 64


def test_only_an_mcp_implementation_is_pinned() -> None:
    with pytest.raises(ValueError) as raised:
        mcp_tool_document(unpinned().model_copy(update={"mcp": None}), SEARCH)

    assert str(raised.value) == "Only an MCP implementation can be pinned."


def test_an_unpinned_implementation_is_refused_as_an_implementation_would_be() -> None:
    with pytest.raises(ValidationError):
        unpinned(environment=("TOKEN",))


# The command


def test_the_command_prints_the_document_of_the_listed_tool(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out, err = written(capsys)

    assert (status, err) == (0, "")
    assert decode_tool_document(out) == mcp_tool_document(unpinned(), SEARCH)


def test_the_command_prints_a_text_tools_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out, _ = written(capsys, tool="greet")

    assert status == 0
    assert decode_tool_document(out).definition.output_schema.json_schema == (
        MCP_TEXT_OUTPUT_SCHEMA
    )


def test_a_tool_the_server_does_not_serve_is_named(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert written(capsys, tool="nope") == (
        1,
        "",
        f"MCP server {URL} serves no tool named 'nope'.\n",
    )


def test_the_server_is_named_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert written(capsys, command=("search-server",)) == (
        1,
        "",
        f"{SERVER_NAMED_TWICE_MESSAGE}\n",
    )
    assert written(capsys, url=None) == (1, "", f"{SERVER_NOT_NAMED_MESSAGE}\n")
    assert SERVER_NAMED_TWICE_MESSAGE == (
        "Name the MCP server with --url or with a command after --, not both."
    )
    assert SERVER_NOT_NAMED_MESSAGE == "Name the MCP server with --url, or with a command after --."


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        pytest.param(
            {"grants": ("TOKEN",)},
            "An MCP tool implementation whose server is reached over HTTP starts no process, so "
            "it may not grant environment variables.",
            id="http-grants",
        ),
        pytest.param(
            {"url": "ftp://mcp.example.com"},
            "MCP server URL 'ftp://mcp.example.com' must be an http or https URL.",
            id="a-bad-url",
        ),
        pytest.param(
            {"url": None, "command": ("server",), "authorization": "TOKEN"},
            "Only an MCP server reached over HTTP takes an authorization variable; a stdio "
            "server is given its credentials as environment grants.",
            id="stdio-authorization",
        ),
    ],
)
def test_a_binding_that_could_not_be_declared_is_refused_saying_why(
    capsys: pytest.CaptureFixture[str],
    options: dict[str, Any],
    reason: str,
) -> None:
    assert written(capsys, **options) == (1, "", f"{reason}\n")


def test_a_refusal_of_a_field_names_where_it_is(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert written(capsys, tool="") == (
        1,
        "",
        "tool: String should have at least 1 character\n",
    )


def test_an_authorization_variable_that_is_not_set_is_named(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEARCH_TOKEN", raising=False)

    assert written(capsys, authorization="SEARCH_TOKEN") == (
        1,
        "",
        f"MCP tool 'search' on {URL} needs its authorization variable SEARCH_TOKEN, which is "
        "not set.\n",
    )


def test_a_server_that_cannot_be_reached_is_named(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unreachable(
        connection: McpConnection,
    ) -> Any:
        raise ConnectionRefusedError("Connection refused")

    assert written(capsys, connect=unreachable) == (
        1,
        "",
        f"MCP server {URL} could not be listed: Connection refused\n",
    )


def slow_server() -> Server[Any]:
    """Return a server that takes too long to list its tools."""

    async def list_tools(
        context: ServerRequestContext[Any],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        await asyncio.sleep(30)

        return types.ListToolsResult(tools=[])

    return Server("slow", on_list_tools=list_tools)


def test_a_server_that_lists_too_slowly_is_named(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert written(capsys, connect=lambda connection: slow_server(), timeout_seconds=0.2) == (
        1,
        "",
        f"MCP server {URL} did not list its tools within 0.2 seconds.\n",
    )


def test_listing_without_a_named_timeout_is_given_thirty_seconds() -> None:
    assert LISTING_TIMEOUT_SECONDS == 30.0


def test_listing_is_given_the_named_timeout_and_the_document_keeps_it(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeouts: list[float | None] = []
    served = McpToolExecutor.served_tool

    async def recording(
        executor: McpToolExecutor,
        implementation: Any,
    ) -> McpListedTool | None:
        timeouts.append(implementation.timeout_seconds)

        return await served(executor, implementation)

    monkeypatch.setattr(McpToolExecutor, "served_tool", recording)

    first = written(capsys)
    second = written(capsys, timeout_seconds=12.0)

    assert timeouts == [LISTING_TIMEOUT_SECONDS, 12.0]
    assert decode_tool_document(first[1]).implementations[0].timeout_seconds is None
    assert decode_tool_document(second[1]).implementations[0].timeout_seconds == 12.0


# A real stdio server, and importing what was written


def test_a_document_written_from_a_stdio_server_imports_and_its_tool_runs(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    status = tool_from_mcp(tool="greet", command=(sys.executable, str(FAKE_SERVER)))
    out = capsys.readouterr().out

    assert status == 0

    document = decode_tool_document(out)
    path = tmp_path / "greet.json"
    path.write_text(out, encoding="utf-8")
    monkeypatch.setenv("AZATHOTH_DATABASE", str(tmp_path / "azathoth.db"))

    assert import_tool(path) == 0

    stored = SQLiteToolRepository(tmp_path / "azathoth.db").get_implementation(
        document.implementations[0].id
    )

    assert stored == document.implementations[0]

    output = asyncio.run(McpToolExecutor().execute(document.implementations[0], {}))

    assert output == {"text": "hello\nworld"}
    assert not json_schema_violations(
        json_schema_validator(document.definition.output_schema.json_schema), output
    )


# Parsing


def test_the_command_is_parsed_with_its_server_after_the_separator() -> None:
    received: dict[str, Any] = {}

    def recorder(
        **arguments: Any,
    ) -> int:
        received.update(arguments)

        return 0

    arguments = build_parser().parse_args(
        [
            "tool",
            "from-mcp",
            "--tool",
            "search",
            "--grant",
            "SEARCH_KEY",
            "--grant",
            "AWS_*",
            "--timeout-seconds",
            "20",
            "--",
            "npx",
            "-y",
            "@acme/search",
        ]
    )

    assert dispatched(arguments, recorder) == 0
    assert received == {
        "tool": "search",
        "url": None,
        "command": ("npx", "-y", "@acme/search"),
        "authorization": None,
        "grants": ("SEARCH_KEY", "AWS_*"),
        "timeout_seconds": 20.0,
    }


def test_the_command_is_parsed_with_a_url_and_its_authorization() -> None:
    received: dict[str, Any] = {}

    def recorder(
        **arguments: Any,
    ) -> int:
        received.update(arguments)

        return 0

    arguments = build_parser().parse_args(
        ["tool", "from-mcp", "--tool", "search", "--url", URL, "--authorization", "TOKEN"]
    )

    assert dispatched(arguments, recorder) == 0
    assert received == {
        "tool": "search",
        "url": URL,
        "command": (),
        "authorization": "TOKEN",
        "grants": (),
        "timeout_seconds": None,
    }


def unused(
    *_arguments: object,
    **_keywords: object,
) -> int:
    """Fail when an unrelated tool handler is dispatched."""

    raise AssertionError("unrelated tool handler should not be dispatched")


def dispatched(
    arguments: Namespace,
    tool_from_mcp: Any,
) -> int | None:
    """Dispatch one tool command with only `from-mcp` live."""

    return dispatch_tool_command(
        arguments,
        export_tool=unused,
        import_tool=unused,
        install_standard_tools=unused,
        list_tool_history=unused,
        list_tool_implementations=unused,
        list_tool_test_cases=unused,
        list_tool_versions=unused,
        list_tools=unused,
        show_tool=unused,
        show_tool_implementation=unused,
        show_tool_test_case=unused,
        tool_usage=unused,
        verify_tool=unused,
        tool_from_mcp=tool_from_mcp,
    )


def test_a_drifted_tools_document_imports_as_the_tools_next_revision(
    tmp_path: Path,
) -> None:
    repository = SQLiteToolRepository(tmp_path / "azathoth.db")
    first = mcp_tool_document(unpinned(), SEARCH)
    drifted = mcp_tool_document(
        unpinned(), SEARCH.model_copy(update={"input_schema": {"type": "object"}})
    )

    assert repository.save_document(first).number == 1
    assert repository.save_document(drifted).number == 2

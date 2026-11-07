"""Tests for binding a tool implementation to a tool an MCP server serves (ADR 0119)."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.revisions import content_digest
from azathoth.tools import (
    MCP_SCHEMA_DIGEST_PATTERN,
    MCP_TOOL_RUNTIME,
    PROCESS_TOOL_RUNTIME,
    PYTHON_TOOL_RUNTIME,
    McpCredentials,
    McpServer,
    McpToolBinding,
    ProcessToolExecutor,
    PythonToolExecutor,
    ToolDefinition,
    ToolDocument,
    ToolExecutionError,
    ToolImplementation,
    ToolInputSchema,
    ToolOutputSchema,
    decode_tool_document,
    encode_tool_document,
    mcp_schema_digest,
)

PROJECT_ROOT = Path(__file__).parents[2]

STANDARD_TOOLS = PROJECT_ROOT / "src" / "azathoth" / "standard" / "tools"

TOOL_ID = UUID("01190000-0000-4000-8000-000000000001")

IMPLEMENTATION_ID = UUID("01190000-0000-4000-8000-000000000002")

INPUT_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}

DIGEST = mcp_schema_digest(INPUT_SCHEMA, None)

STDIO = McpServer(command=("npx", "-y", "@acme/search-server"))

HTTP = McpServer(url="https://mcp.example.com/mcp")


def binding(
    server: McpServer = STDIO,
    **fields: Any,
) -> McpToolBinding:
    """Return a binding to the search tool some server serves."""

    return McpToolBinding(**{"server": server, "tool": "search", "schema_digest": DIGEST, **fields})


def implementation(
    **fields: Any,
) -> ToolImplementation:
    """Return an MCP implementation of the search tool, with some fields."""

    return ToolImplementation(
        **{
            "id": IMPLEMENTATION_ID,
            "tool_id": TOOL_ID,
            "tool_version": "1.0.0",
            "runtime": MCP_TOOL_RUNTIME,
            "mcp": binding(),
            **fields,
        }
    )


def refusal(
    model: type[McpServer | McpCredentials | McpToolBinding | ToolImplementation],
    **fields: Any,
) -> str:
    """Return the first message a model is refused with."""

    with pytest.raises(ValidationError) as raised:
        model.model_validate(fields)

    return str(raised.value.errors()[0]["msg"]).removeprefix("Value error, ")


def implementation_refusal(
    **fields: Any,
) -> str:
    """Return the message an MCP implementation with some fields is refused with."""

    return refusal(
        ToolImplementation,
        **{
            "tool_id": TOOL_ID,
            "tool_version": "1.0.0",
            "runtime": MCP_TOOL_RUNTIME,
            "mcp": binding().model_dump(mode="json"),
            **fields,
        },
    )


# The schema digest


def test_a_schema_digest_is_the_sha256_of_the_canonical_schemas() -> None:
    canonical = (
        '{"inputSchema":{"properties":{"query":{"type":"string"}},"required":["query"],'
        '"type":"object"},"outputSchema":null}'
    )

    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == DIGEST


def test_a_schema_digest_ignores_key_order_and_names_the_output_schema() -> None:
    reordered: JsonValue = {
        "required": ["query"],
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }

    assert mcp_schema_digest(reordered, None) == DIGEST
    assert mcp_schema_digest(INPUT_SCHEMA, {"type": "object"}) != DIGEST


def test_a_schema_digest_keeps_unicode_as_written() -> None:
    schema: JsonValue = {"description": "café"}
    canonical = '{"inputSchema":{"description":"café"},"outputSchema":null}'

    assert mcp_schema_digest(schema, None) == hashlib.sha256(canonical.encode()).hexdigest()


def test_the_digest_pattern_is_lowercase_sha256_hex() -> None:
    assert MCP_SCHEMA_DIGEST_PATTERN == r"^[0-9a-f]{64}$"


# Servers


def test_a_server_is_a_stdio_command_or_an_http_url() -> None:
    assert STDIO.is_stdio is True
    assert HTTP.is_stdio is False
    assert STDIO.describe() == "npx -y @acme/search-server"
    assert McpServer(command=("my server", "--flag")).describe() == "'my server' --flag"
    assert HTTP.describe() == "https://mcp.example.com/mcp"


def test_a_server_serializes_only_its_transport() -> None:
    assert STDIO.model_dump(mode="json") == {"command": ["npx", "-y", "@acme/search-server"]}
    assert HTTP.model_dump(mode="json") == {"url": "https://mcp.example.com/mcp"}


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({}, id="neither"),
        pytest.param({"command": ["server"], "url": "https://x.example"}, id="both"),
    ],
)
def test_a_server_names_exactly_one_transport(
    fields: dict[str, Any],
) -> None:
    assert refusal(McpServer, **fields) == (
        "An MCP server is named by exactly one of a command or a URL."
    )


def test_a_server_command_has_no_empty_argument() -> None:
    assert refusal(McpServer, command=["server", ""]) == (
        "MCP server command arguments cannot be empty."
    )


def test_a_server_command_is_not_empty() -> None:
    with pytest.raises(ValidationError):
        McpServer(command=())


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("ftp://mcp.example.com", id="another-scheme"),
        pytest.param("https://", id="no-host"),
        pytest.param("mcp.example.com/mcp", id="no-scheme"),
    ],
)
def test_a_server_url_is_an_http_or_https_url(
    url: str,
) -> None:
    assert refusal(McpServer, url=url) == f"MCP server URL {url!r} must be an http or https URL."


def test_a_plain_http_url_is_accepted() -> None:
    assert McpServer(url="http://localhost:8000/mcp").describe() == "http://localhost:8000/mcp"


# Credentials


def test_credentials_name_an_authorization_variable_exactly() -> None:
    assert McpCredentials(authorization="SEARCH_TOKEN").authorization == "SEARCH_TOKEN"

    for name in ("SEARCH_*", "1TOKEN", "SEARCH-TOKEN"):
        assert refusal(McpCredentials, authorization=name) == (
            f"Authorization variable {name!r} must be a variable name of letters, digits and "
            "underscores."
        )


def test_credentials_serialize_only_what_they_name() -> None:
    assert McpCredentials().model_dump(mode="json") == {}
    assert McpCredentials(authorization="TOKEN").model_dump(mode="json") == {
        "authorization": "TOKEN"
    }


# Bindings


def test_a_binding_without_credentials_serializes_without_them() -> None:
    assert binding().model_dump(mode="json") == {
        "server": {"command": ["npx", "-y", "@acme/search-server"]},
        "tool": "search",
        "schema_digest": DIGEST,
    }


def test_a_binding_with_credentials_serializes_them() -> None:
    dumped = binding(HTTP, credentials=McpCredentials(authorization="TOKEN")).model_dump(
        mode="json"
    )

    assert dumped["credentials"] == {"authorization": "TOKEN"}
    assert McpToolBinding.model_validate(dumped).credentials.authorization == "TOKEN"


@pytest.mark.parametrize(
    "digest",
    [
        pytest.param(DIGEST.upper(), id="uppercase"),
        pytest.param(DIGEST[:-1], id="short"),
        pytest.param(f"sha256:{DIGEST}", id="prefixed"),
    ],
)
def test_a_binding_pins_a_lowercase_sha256_digest(
    digest: str,
) -> None:
    assert refusal(
        McpToolBinding, server={"url": "https://x.example"}, tool="search", schema_digest=digest
    ) == ("An MCP tool's schema digest must be a sha256 digest of 64 lowercase hex characters.")


def test_a_binding_names_its_tool() -> None:
    with pytest.raises(ValidationError):
        McpToolBinding(server=HTTP, tool="", schema_digest=DIGEST)


def test_only_an_http_server_takes_an_authorization_variable() -> None:
    assert refusal(
        McpToolBinding,
        server={"command": ["server"]},
        tool="search",
        schema_digest=DIGEST,
        credentials={"authorization": "TOKEN"},
    ) == (
        "Only an MCP server reached over HTTP takes an authorization variable; a stdio server "
        "is given its credentials as environment grants."
    )


# Implementations


def test_an_mcp_implementation_serializes_its_binding_and_nothing_it_cannot_declare() -> None:
    assert implementation().model_dump(mode="json") == {
        "id": str(IMPLEMENTATION_ID),
        "tool_id": str(TOOL_ID),
        "tool_version": "1.0.0",
        "version": "1.0.0",
        "runtime": "mcp",
        "mcp": binding().model_dump(mode="json"),
    }


def test_an_mcp_implementation_round_trips() -> None:
    timed = implementation(timeout_seconds=20.0, environment=("SEARCH_API_KEY",))

    assert ToolImplementation.model_validate(timed.model_dump(mode="json")) == timed


def test_an_mcp_implementation_declares_a_binding() -> None:
    assert implementation_refusal(mcp=None) == (
        "MCP tool implementations must declare an MCP binding."
    )


def test_an_mcp_implementation_declares_no_source() -> None:
    assert implementation_refusal(source="print(1)") == (
        "An MCP tool implementation runs the tool its binding names, so it declares no source."
    )


def test_an_mcp_implementation_declares_no_entrypoint() -> None:
    assert implementation_refusal(entrypoint="run") == (
        "An MCP tool implementation runs the tool its binding names, so it declares no entrypoint."
    )


@pytest.mark.parametrize("runtime", [PROCESS_TOOL_RUNTIME, PYTHON_TOOL_RUNTIME])
def test_only_an_mcp_implementation_declares_a_binding(
    runtime: str,
) -> None:
    assert implementation_refusal(runtime=runtime, source="x", command=["bash"]) == (
        "Only MCP tool implementations may declare an MCP binding."
    )


def test_every_other_implementation_declares_a_source() -> None:
    assert implementation_refusal(runtime=PYTHON_TOOL_RUNTIME, mcp=None) == (
        "Tool implementations other than MCP ones must declare a source."
    )


def test_an_mcp_implementation_may_declare_a_timeout_and_no_command() -> None:
    assert implementation(timeout_seconds=20.0).timeout_seconds == 20.0
    assert implementation_refusal(command=["bash"]) == (
        "Only process tool implementations may declare a command."
    )


def test_an_mcp_implementation_whose_server_it_starts_may_grant_variables() -> None:
    assert implementation(environment=("SEARCH_*",)).environment == ("SEARCH_*",)


def test_an_mcp_implementation_reaching_its_server_over_http_grants_none() -> None:
    assert implementation_refusal(
        mcp=binding(HTTP).model_dump(mode="json"), environment=["TOKEN"]
    ) == (
        "An MCP tool implementation whose server is reached over HTTP starts no process, so it "
        "may not grant environment variables."
    )


def test_an_mcp_implementation_takes_no_content_inputs() -> None:
    assert implementation_refusal(content_inputs=["document"]) == (
        "Only process tool implementations may take content inputs."
    )


def test_an_mcp_implementations_digest_covers_its_binding() -> None:
    assert content_digest(implementation()) != content_digest(implementation(mcp=binding(HTTP)))
    assert content_digest(implementation()) != content_digest(
        implementation(mcp=binding(tool="lookup"))
    )


# Documents


def test_a_tool_document_round_trips_an_mcp_implementation() -> None:
    document = ToolDocument(
        definition=ToolDefinition(
            id=TOOL_ID,
            name="search",
            description="Search the catalog.",
            version="1.0.0",
            input_schema=ToolInputSchema(json_schema=INPUT_SCHEMA),
            output_schema=ToolOutputSchema(json_schema={"type": "object"}),
        ),
        implementations=(implementation(mcp=binding(HTTP, credentials={"authorization": "T"})),),
    )

    assert decode_tool_document(encode_tool_document(document)) == document


@pytest.mark.parametrize(
    "path",
    [pytest.param(path, id=path.name) for path in sorted(STANDARD_TOOLS.glob("*.json"))],
)
def test_every_standard_tool_document_serializes_as_it_is_written(
    path: Path,
) -> None:
    written = json.loads(path.read_text(encoding="utf-8"))

    assert decode_tool_document(path.read_text(encoding="utf-8")).model_dump(mode="json") == (
        written
    )


# Executors that run source


def sourceless(
    runtime: str,
) -> ToolImplementation:
    """Return an implementation of some runtime without a source, unvalidated."""

    return ToolImplementation.model_construct(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=runtime,
        entrypoint="run",
        command=("bash",) if runtime == PROCESS_TOOL_RUNTIME else None,
        timeout_seconds=None,
        environment=(),
        content_inputs=(),
        extraction_output=None,
        source=None,
        mcp=None,
    )


@pytest.mark.parametrize(
    "executor",
    [
        pytest.param(ProcessToolExecutor(), id="process"),
        pytest.param(PythonToolExecutor(), id="python"),
    ],
)
def test_an_executor_running_source_refuses_an_implementation_without_one(
    executor: ProcessToolExecutor | PythonToolExecutor,
) -> None:
    runtime = PROCESS_TOOL_RUNTIME if isinstance(executor, ProcessToolExecutor) else "python"

    with pytest.raises(ToolExecutionError) as raised:
        asyncio.run(executor.execute(sourceless(runtime), {}))

    assert str(raised.value) == (
        f"Tool implementation {IMPLEMENTATION_ID} does not declare a source."
    )

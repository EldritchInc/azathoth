"""Tests for the MCP server, through the SDK's in-process client (ADR 0111)."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

import mcp_types as types
from mcp import Client
from mcp.server.lowlevel import Server
from pydantic import JsonValue

from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import FixedModelSelection, PromptStrategySpec
from azathoth.providers import Prompt, ProviderModel
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from azathoth_mcp import __version__
from azathoth_mcp.access import (
    READ_SCOPE,
    STDIO_CALLER,
    McpCaller,
    Transport,
    invoke_scope,
)
from azathoth_mcp.catalog import (
    GET_INVOCATION_DESCRIPTION,
    GET_INVOCATION_SCHEMA,
    ToolCatalog,
    workflow_output_schema,
    workflow_tool_schema,
)
from azathoth_mcp.exposure import ExposedWorkflow, ExposureDocument
from azathoth_mcp.server import (
    GET_INVOCATION_ANNOTATIONS,
    SERVER_NAME,
    UNEXPECTED_FAILURE_MESSAGE,
    WORKFLOW_TOOL_ANNOTATIONS,
    build_server,
)
from azathoth_mcp.service import ToolService
from tests.api.test_models import StaticDirectory
from tests.mcp.test_service import instance_serving

SUMMARIZE_ID = UUID("7d1f3c2a-0b8e-4c55-9a61-2f0d6c1e9b44")

TRIAGE_ID = UUID("0c9e6a52-5d1b-4f7e-8a3c-91b2d4e6f708")

PRIMARY = FixedModelSelection(provider="test-provider", model="production-model")

MISSING = FixedModelSelection(provider="test-provider", model="missing-model")

TICKET_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {"ticket": {"type": "string"}},
    "required": ["ticket"],
}

EXPOSURE = ExposureDocument(
    version=1,
    tools=(
        ExposedWorkflow(
            workflow_id=SUMMARIZE_ID,
            name="summarize",
            description="Summarize a ticket.",
            input_schema=TICKET_SCHEMA,
        ),
        ExposedWorkflow(
            workflow_id=TRIAGE_ID,
            name="triage",
            description="Triage a ticket.",
        ),
    ),
)

Result = TypeVar("Result")


def production_state(
    workflow_id: UUID,
    selection: FixedModelSelection,
) -> WorkflowProductionState:
    """Return a two-step production state of one workflow."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=workflow_id,
                name=f"workflow-{workflow_id}",
                description="Exercise the server.",
            ),
            steps=tuple(
                WorkflowStepSpecification(
                    id=UUID(int=100 + number),
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=UUID(int=200 + number),
                            name=f"step-{number}",
                            description="Exercise the server.",
                        ),
                        prompt=Prompt(text="Summarize."),
                        model_selection=selection,
                    ),
                )
                for number in (1, 2)
            ),
        ),
    )


class BrokenDirectory(StaticDirectory):
    """A provider directory that fails with a secret in its message."""

    async def models(
        self,
    ) -> tuple[ProviderModel, ...]:
        """Fail as a server's own bug would."""

        raise RuntimeError("password=hunter2")


def service_over(
    tmp_path: Path,
    *,
    broken: bool = False,
) -> ToolService:
    """Return a tool service over a fresh database with two active workflows."""

    database = tmp_path / "azathoth.db"
    stores = open_repositories(database)
    stores.production_states.set(production_state(SUMMARIZE_ID, PRIMARY))
    stores.production_states.set(production_state(TRIAGE_ID, MISSING))

    return ToolService(
        catalog=ToolCatalog(EXPOSURE, stores.production_states),
        instance=instance_serving(
            database,
            PRIMARY,
            directory=BrokenDirectory(PRIMARY.provider, ()) if broken else None,
        ),
    )


def with_client(
    server: Server[Any],
    use: Callable[[Client], Awaitable[Result]],
) -> Result:
    """Connect the SDK's in-process client to a server, and use it."""

    async def run() -> Result:
        async with Client(server) as client:
            return await use(client)

    return asyncio.run(run())


def call(
    server: Server[Any],
    name: str,
    arguments: dict[str, Any],
) -> types.CallToolResult:
    """Call one tool through a client."""

    async def use(client: Client) -> types.CallToolResult:
        return await client.call_tool(name, arguments)

    return with_client(server, use)


def listed(
    server: Server[Any],
) -> list[types.Tool]:
    """Return the tools a client is offered."""

    async def use(client: Client) -> list[types.Tool]:
        return (await client.list_tools()).tools

    return with_client(server, use)


def text_of(
    result: types.CallToolResult,
) -> str:
    """Return the one text block of a tool result."""

    (block,) = result.content

    assert isinstance(block, types.TextContent)

    return block.text


def stdio_server_over(
    tmp_path: Path,
) -> Server[Any]:
    """Return a server over a fresh database, answering the stdio caller."""

    return build_server(service_over(tmp_path), caller_of=lambda: STDIO_CALLER)


def test_the_server_names_itself_and_its_version(
    tmp_path: Path,
) -> None:
    server = stdio_server_over(tmp_path)

    assert server.name == SERVER_NAME == "azathoth"
    assert server.version == __version__


def test_every_tool_is_listed_with_its_schema_and_hints(
    tmp_path: Path,
) -> None:
    tools = listed(stdio_server_over(tmp_path))

    assert tools == [
        types.Tool(
            name="summarize",
            description="Summarize a ticket.",
            input_schema=workflow_tool_schema(EXPOSURE.tools[0]),
            output_schema=workflow_output_schema(None),
            annotations=WORKFLOW_TOOL_ANNOTATIONS,
        ),
        types.Tool(
            name="triage",
            description="Triage a ticket.",
            input_schema=workflow_tool_schema(EXPOSURE.tools[1]),
            output_schema=workflow_output_schema(None),
            annotations=WORKFLOW_TOOL_ANNOTATIONS,
        ),
        types.Tool(
            name="get_invocation",
            description=GET_INVOCATION_DESCRIPTION,
            input_schema=GET_INVOCATION_SCHEMA,
            annotations=GET_INVOCATION_ANNOTATIONS,
        ),
    ]


def test_workflow_tools_are_not_read_only_and_get_invocation_is() -> None:
    assert WORKFLOW_TOOL_ANNOTATIONS.read_only_hint is False
    assert WORKFLOW_TOOL_ANNOTATIONS.idempotent_hint is False
    assert WORKFLOW_TOOL_ANNOTATIONS.destructive_hint is False
    assert WORKFLOW_TOOL_ANNOTATIONS.open_world_hint is True
    assert GET_INVOCATION_ANNOTATIONS.read_only_hint is True
    assert GET_INVOCATION_ANNOTATIONS.idempotent_hint is True
    assert GET_INVOCATION_ANNOTATIONS.open_world_hint is False


def test_a_call_returns_its_outcome_as_structured_content_and_text(
    tmp_path: Path,
) -> None:
    result = call(
        stdio_server_over(tmp_path),
        "summarize",
        {"input": {"ticket": "Printer on fire."}, "idempotency_key": "ticket-42"},
    )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["status"] == "succeeded"
    assert result.structured_content["idempotency_key"] == "ticket-42"
    assert result.structured_content["error"] is None
    assert UUID(result.structured_content["invocation_id"])
    assert json.loads(text_of(result)) == result.structured_content


def test_a_failed_invocation_is_an_error_result_with_its_outcome(
    tmp_path: Path,
) -> None:
    result = call(stdio_server_over(tmp_path), "triage", {"input": "x"})

    assert result.is_error is True
    assert result.structured_content is not None
    assert result.structured_content["status"] == "failed"
    assert result.structured_content["error"]["code"] == "model_unavailable"


def test_progress_reaches_a_client_that_asks_for_it(
    tmp_path: Path,
) -> None:
    reports: list[tuple[float, float | None, str | None]] = []

    async def on_progress(
        progress: float,
        total: float | None,
        message: str | None,
    ) -> None:
        reports.append((progress, total, message))

    async def use(client: Client) -> types.CallToolResult:
        return await client.call_tool(
            "summarize", {"input": {"ticket": "x"}}, progress_callback=on_progress
        )

    result = with_client(stdio_server_over(tmp_path), use)

    assert result.is_error is False
    assert reports == [
        (1.0, 2.0, "1 of 2 steps finished."),
        (2.0, 2.0, "2 of 2 steps finished."),
    ]


def test_get_invocation_returns_the_evidence_of_a_call(
    tmp_path: Path,
) -> None:
    server = stdio_server_over(tmp_path)

    async def use(client: Client) -> tuple[types.CallToolResult, types.CallToolResult]:
        made = await client.call_tool("summarize", {"input": {"ticket": "x"}})

        assert made.structured_content is not None

        read = await client.call_tool(
            "get_invocation", {"invocation_id": made.structured_content["invocation_id"]}
        )

        return made, read

    made, read = with_client(server, use)

    assert made.structured_content is not None
    assert read.is_error is False
    assert read.structured_content is not None
    assert read.structured_content["invocation_id"] == made.structured_content["invocation_id"]
    assert read.structured_content["tool"] == "summarize"
    assert read.structured_content["input"] == {"ticket": "x"}
    assert read.structured_content["caller"] == {"mcp": {"transport": "stdio", "tool": "summarize"}}
    assert len(read.structured_content["run"]["steps"]) == 2
    assert json.loads(text_of(read)) == read.structured_content


def test_a_refused_call_is_an_error_result_the_model_can_read(
    tmp_path: Path,
) -> None:
    server = stdio_server_over(tmp_path)

    refusals = {
        "unknown": call(server, "summarise", {"input": 1}),
        "arguments": call(server, "summarize", {"input": {}}),
        "invocation": call(server, "get_invocation", {"invocation_id": str(SUMMARIZE_ID)}),
    }

    assert {name: result.is_error for name, result in refusals.items()} == {
        "unknown": True,
        "arguments": True,
        "invocation": True,
    }
    assert {name: text_of(result) for name, result in refusals.items()} == {
        "unknown": 'There is no tool named "summarise".',
        "arguments": (
            'The arguments of "summarize" are not valid: '
            "$.input: 'ticket' is a required property."
        ),
        "invocation": f"No invocation {SUMMARIZE_ID} was found.",
    }
    assert all(result.structured_content is None for result in refusals.values())


def test_a_call_without_arguments_is_refused_for_its_missing_input(
    tmp_path: Path,
) -> None:
    async def use(client: Client) -> types.CallToolResult:
        return await client.call_tool("summarize")

    result = with_client(stdio_server_over(tmp_path), use)

    assert result.is_error is True
    assert text_of(result) == (
        "The arguments of \"summarize\" are not valid: $: 'input' is a required property."
    )


def test_an_unexpected_failure_is_reported_without_its_details(
    tmp_path: Path,
) -> None:
    server = build_server(service_over(tmp_path, broken=True), caller_of=lambda: STDIO_CALLER)

    result = call(server, "summarize", {"input": {"ticket": "x"}})

    assert result.is_error is True
    assert text_of(result) == UNEXPECTED_FAILURE_MESSAGE
    assert "hunter2" not in text_of(result)


def test_a_caller_is_offered_only_what_its_token_allows(
    tmp_path: Path,
) -> None:
    invoker = McpCaller(
        transport=Transport.HTTP, subject="alice", scopes=frozenset({invoke_scope("triage")})
    )
    reader = McpCaller(
        transport=Transport.HTTP,
        subject="alice",
        scopes=frozenset({invoke_scope("summarize"), READ_SCOPE}),
    )
    nobody = McpCaller(transport=Transport.HTTP, subject="alice", scopes=frozenset())

    service = service_over(tmp_path)

    def names(
        caller: McpCaller,
    ) -> list[str]:
        return [tool.name for tool in listed(build_server(service, caller_of=lambda: caller))]

    assert names(invoker) == ["triage"]
    assert names(reader) == ["summarize", "get_invocation"]
    assert names(nobody) == []


def test_reading_every_invocation_also_offers_get_invocation(
    tmp_path: Path,
) -> None:
    auditor = McpCaller(
        transport=Transport.HTTP, subject="carol", scopes=frozenset({"azathoth:read:all"})
    )

    tools = listed(build_server(service_over(tmp_path), caller_of=lambda: auditor))

    assert [tool.name for tool in tools] == ["get_invocation"]


def test_a_tool_the_token_does_not_allow_is_refused_by_its_scope(
    tmp_path: Path,
) -> None:
    caller = McpCaller(
        transport=Transport.HTTP, subject="alice", scopes=frozenset({invoke_scope("triage")})
    )
    server = build_server(service_over(tmp_path), caller_of=lambda: caller)

    result = call(server, "summarize", {"input": {"ticket": "x"}})

    assert result.is_error is True
    assert text_of(result) == 'This call needs the scope "azathoth:invoke:summarize".'

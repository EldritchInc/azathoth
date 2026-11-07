"""Tests that ADR 0119 shows an MCP implementation Azathoth accepts."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.tools import (
    MCP_TOOL_RUNTIME,
    McpCredentials,
    McpServer,
    McpToolBinding,
    ToolExecutionError,
    ToolImplementation,
    mcp_schema_digest,
)
from azathoth.tools.mcp_execution import McpToolExecutor, McpUnavailableError
from tests.tools.mcp_fake_server import FAILURE_TEXT, build_fake_server, tools

ROOT = Path(__file__).parents[2]

ADR = ROOT / "docs" / "adrs" / "0119-call-mcp-served-tools.md"


def decision_blocks(
    language: str,
) -> list[str]:
    """Return the ADR's Decision blocks in one language."""

    text = ADR.read_text(encoding="utf-8")
    decision = text[text.index("## Decision") : text.index("## Consequences")]

    return [block.split("```", 1)[0] for block in decision.split(f"```{language}\n")[1:]]


def test_the_adr_shows_an_mcp_implementation_azathoth_accepts() -> None:
    (shown,) = decision_blocks("json")
    implementation = ToolImplementation.model_validate_json(
        shown.replace("<IMPLEMENTATION_ID>", str(UUID(int=1)))
        .replace("<TOOL_ID>", str(UUID(int=2)))
        .replace("<SCHEMA_DIGEST>", mcp_schema_digest({"type": "object"}, None))
    )

    assert implementation.runtime == MCP_TOOL_RUNTIME
    assert implementation.mcp is not None
    assert implementation.mcp.credentials.authorization == "SEARCH_TOKEN"
    assert json.loads(shown).keys() == implementation.model_dump(mode="json").keys()


def test_the_adr_is_listed_in_the_index() -> None:
    index = (ROOT / "docs" / "adrs" / "README.md").read_text(encoding="utf-8")

    assert "- [ADR 0119: Call MCP-Served Tools](0119-call-mcp-served-tools.md)\n" in index


# The refusals the ADR quotes


URL = "https://mcp.example.com/mcp"


def message_of(
    tool: str,
    *,
    drift: bool = False,
    authorization: str | None = None,
    digest: str | None = None,
) -> str:
    """Return the message one call of the fake server's tool fails with, values held."""

    if digest is None:
        (listed,) = (listed for listed in tools(drift=False) if listed.name == tool)
        digest = mcp_schema_digest(listed.input_schema, listed.output_schema)

    pin = digest
    implementation = ToolImplementation(
        tool_id=UUID(int=2),
        tool_version="1.0.0",
        runtime=MCP_TOOL_RUNTIME,
        mcp=McpToolBinding(
            server=McpServer(url=URL),
            tool=tool,
            schema_digest=pin,
            credentials=McpCredentials(authorization=authorization),
        ),
    )

    with pytest.raises(ToolExecutionError) as raised:
        asyncio.run(
            McpToolExecutor(
                connect=lambda connection: build_fake_server(drift=drift),
                environ={},
                trace_context=dict,
            ).execute(implementation, {"query": "x"})
        )

    drifted = tools(drift=True)[0]

    return (
        str(raised.value)
        .replace(URL, "<SERVER>")
        .replace(repr(tool), "<TOOL>")
        .replace(pin, "<PINNED>")
        .replace(mcp_schema_digest(drifted.input_schema, drifted.output_schema), "<SERVED>")
        .replace(FAILURE_TEXT, "<REASON>")
        .replace(str(authorization), "<VARIABLE>")
    )


def unavailable() -> str:
    """Return the message a call fails with where the SDK is not installed."""

    return str(McpUnavailableError())


DOCUMENTED: list[tuple[str, Callable[[], str]]] = [
    (
        "MCP server <SERVER> serves no tool named <TOOL>.",
        lambda: message_of("nope", digest=mcp_schema_digest({}, None)),
    ),
    (
        "MCP tool <TOOL> on <SERVER> no longer matches its pinned schemas: pinned <PINNED>, "
        "served <SERVED>.",
        lambda: message_of("search", drift=True),
    ),
    ("MCP tool <TOOL> on <SERVER> failed: <REASON>", lambda: message_of("fail")),
    (
        "MCP tool <TOOL> on <SERVER> needs its authorization variable <VARIABLE>, which is not "
        "set.",
        lambda: message_of("search", authorization="SEARCH_TOKEN"),
    ),
    (
        "MCP tools need the mcp package, which is not installed; install azathoth-ai[mcp].",
        unavailable,
    ),
]
"""Each message ADR 0119 quotes, and what produces it."""


@pytest.mark.parametrize(
    ("documented", "produce"),
    [pytest.param(*row, id=row[0][:48]) for row in DOCUMENTED],
)
def test_the_adr_quotes_the_real_message(
    documented: str,
    produce: Callable[[], str],
) -> None:
    assert f"\n{documented}\n" in ADR.read_text(encoding="utf-8")
    assert produce() == documented


def test_the_adr_quotes_no_text_the_tests_do_not_check() -> None:
    quoted = {line for block in decision_blocks("text") for line in block.splitlines()}

    assert quoted == {documented for documented, _ in DOCUMENTED}

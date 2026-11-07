"""Tests that ADR 0119 shows an MCP implementation Azathoth accepts."""

import json
from pathlib import Path
from uuid import UUID

from azathoth.tools import MCP_TOOL_RUNTIME, ToolImplementation, mcp_schema_digest

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

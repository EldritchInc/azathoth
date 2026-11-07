"""Tests for showing an MCP implementation's binding (ADR 0119)."""

from pathlib import Path

import pytest

from azathoth.cli import show_tool_implementation
from azathoth.tools import (
    McpCredentials,
    McpServer,
    McpToolBinding,
    SQLiteToolRepository,
    ToolDocument,
    ToolImplementation,
    mcp_schema_digest,
)
from tests.cli.test_tool_import import (
    IMPLEMENTATION_ID,
    TOOL_ID,
    configure_database,
    create_definition,
)

DIGEST = mcp_schema_digest({"type": "object"}, None)


def shown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    implementation: ToolImplementation,
) -> str:
    """Store the word-count tool with one MCP implementation, then show it."""

    configure_database(database=tmp_path / "azathoth.db", monkeypatch=monkeypatch)

    SQLiteToolRepository(tmp_path / "azathoth.db").save_document(
        ToolDocument(definition=create_definition(), implementations=(implementation,))
    )

    assert show_tool_implementation(IMPLEMENTATION_ID) == 0

    captured = capsys.readouterr()

    assert captured.err == ""

    return captured.out


def mcp_implementation(
    binding: McpToolBinding,
    **fields: object,
) -> ToolImplementation:
    """Return an MCP implementation of the word-count tool."""

    return ToolImplementation.model_validate(
        {
            "id": IMPLEMENTATION_ID,
            "tool_id": TOOL_ID,
            "tool_version": "1.0.0",
            "runtime": "mcp",
            "mcp": binding,
            **fields,
        }
    )


def test_a_stdio_binding_is_shown_after_the_grants_without_a_source_or_entrypoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = shown(
        tmp_path,
        monkeypatch,
        capsys,
        mcp_implementation(
            McpToolBinding(
                server=McpServer(command=("npx", "-y", "@acme/count server")),
                tool="count",
                schema_digest=DIGEST,
            ),
            timeout_seconds=20.0,
            environment=("COUNT_API_KEY",),
        ),
    )

    assert out.endswith(
        "Runtime: mcp\n"
        "Timeout: 20 seconds\n"
        "Environment: COUNT_API_KEY\n"
        "MCP Server: npx -y '@acme/count server'\n"
        "MCP Tool: count\n"
        f"Schema Digest: {DIGEST}\n"
    )


def test_an_http_binding_names_its_authorization_variable_and_never_a_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("COUNT_TOKEN", "secret-value")

    out = shown(
        tmp_path,
        monkeypatch,
        capsys,
        mcp_implementation(
            McpToolBinding(
                server=McpServer(url="https://mcp.example.com/mcp"),
                tool="count",
                schema_digest=DIGEST,
                credentials=McpCredentials(authorization="COUNT_TOKEN"),
            )
        ),
    )

    assert out.endswith(
        "Runtime: mcp\n"
        "MCP Server: https://mcp.example.com/mcp\n"
        "MCP Tool: count\n"
        f"Schema Digest: {DIGEST}\n"
        "Authorization: COUNT_TOKEN\n"
    )
    assert "secret-value" not in out

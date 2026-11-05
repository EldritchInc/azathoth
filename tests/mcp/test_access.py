"""Tests for callers, their scopes and what they record (ADR 0111)."""

import pytest
from pydantic import JsonValue, ValidationError

from azathoth_mcp.access import (
    CALLER_METADATA_KEY,
    READ_ALL_SCOPE,
    READ_SCOPE,
    STDIO_CALLER,
    McpCaller,
    ToolAccessError,
    Transport,
    invoke_scope,
)


def http_caller(
    *scopes: str,
    subject: str | None = "alice",
) -> McpCaller:
    """Return an HTTP caller whose token grants some scopes."""

    return McpCaller(transport=Transport.HTTP, subject=subject, scopes=frozenset(scopes))


def recorded(
    **fields: JsonValue,
) -> dict[str, JsonValue]:
    """Return caller metadata recorded over MCP with some fields."""

    return {CALLER_METADATA_KEY: dict(fields)}


def test_scopes_are_named_per_tool() -> None:
    assert invoke_scope("summarize_ticket") == "azathoth:invoke:summarize_ticket"
    assert READ_SCOPE == "azathoth:read"
    assert READ_ALL_SCOPE == "azathoth:read:all"


def test_the_stdio_caller_may_call_everything() -> None:
    assert STDIO_CALLER.transport is Transport.STDIO
    assert STDIO_CALLER.scopes is None

    STDIO_CALLER.require(invoke_scope("anything"))
    STDIO_CALLER.require(READ_SCOPE)


def test_a_caller_with_the_scope_may_call() -> None:
    http_caller(invoke_scope("summarize")).require(invoke_scope("summarize"))


def test_a_caller_without_the_scope_is_refused_by_name() -> None:
    with pytest.raises(ToolAccessError) as raised:
        http_caller(invoke_scope("triage")).require(invoke_scope("summarize"))

    assert str(raised.value) == 'This call needs the scope "azathoth:invoke:summarize".'


def test_a_token_with_no_scopes_may_call_nothing() -> None:
    with pytest.raises(ToolAccessError):
        http_caller().require(READ_SCOPE)


def test_a_reader_reads_only_its_own_invocations() -> None:
    reader = http_caller(READ_SCOPE)

    assert reader.reads_every_invocation is False
    assert reader.may_read(recorded(transport="http", subject="alice")) is True
    assert reader.may_read(recorded(transport="http", subject="bob")) is False
    assert reader.may_read(recorded(transport="stdio")) is False
    assert reader.may_read({}) is False
    assert reader.may_read({CALLER_METADATA_KEY: "alice"}) is False
    assert reader.may_read({"subject": "alice"}) is False


def test_a_reader_without_a_subject_reads_none() -> None:
    reader = http_caller(READ_SCOPE, subject=None)

    assert reader.may_read(recorded(transport="http")) is False


def test_reading_every_invocation_reads_any() -> None:
    for reader in (http_caller(READ_ALL_SCOPE), STDIO_CALLER):
        assert reader.reads_every_invocation is True
        assert reader.may_read(recorded(transport="http", subject="bob")) is True
        assert reader.may_read({}) is True


def test_a_local_call_records_its_transport_and_tool() -> None:
    assert STDIO_CALLER.caller_metadata("summarize") == {
        "mcp": {"transport": "stdio", "tool": "summarize"}
    }


def test_a_remote_call_records_its_subject_and_client() -> None:
    caller = McpCaller(
        transport=Transport.HTTP,
        subject="alice",
        client_id="claude-desktop",
        scopes=frozenset({"secret-scope"}),
    )

    assert caller.caller_metadata("summarize") == {
        "mcp": {
            "transport": "http",
            "tool": "summarize",
            "subject": "alice",
            "client_id": "claude-desktop",
        }
    }


def test_a_subject_or_client_id_is_never_empty() -> None:
    with pytest.raises(ValidationError):
        McpCaller(transport=Transport.HTTP, subject="")

    with pytest.raises(ValidationError):
        McpCaller(transport=Transport.HTTP, client_id="")

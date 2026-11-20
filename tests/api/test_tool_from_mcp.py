"""Contract tests for making a tool's document from an MCP server's tool (ADR 0133)."""

from typing import Any

import pytest

from azathoth import api
from azathoth.api.browsing import export_name
from azathoth.api.mcp_tools import SERVER_NAMED_TWICE_MESSAGE, SERVER_NOT_NAMED_MESSAGE
from azathoth.tools import decode_tool_document, encode_tool_document
from azathoth.tools.mcp_document import mcp_tool_document
from azathoth.tools.mcp_execution import McpConnection
from tests.cli.test_tool_from_mcp import SEARCH, URL, in_process, unpinned


def made(
    instance: api.Azathoth,
    **options: Any,
) -> api.DocumentExport:
    """Return the document of the fake server's search tool, or of the tool named."""

    return instance.tools.from_mcp(
        options.pop("tool", "search"),
        **{"url": URL, "connect": in_process, **options},
    )


def test_the_document_is_the_listed_tools_pinned_as_it_is_served(
    instance: api.Azathoth,
) -> None:
    exported = made(instance)

    assert exported.text == encode_tool_document(mcp_tool_document(unpinned(), SEARCH)) + "\n"
    assert exported.file_name == "search-1.0.0.tool.json"
    assert exported.sensitivity is None


def test_nothing_is_imported_until_the_document_is(
    instance: api.Azathoth,
) -> None:
    exported = made(instance)

    assert instance.tools.list() == ()

    imported = instance.tools.import_document(exported.text)

    assert imported.created
    assert imported.tool.id == decode_tool_document(exported.text).definition.id


def test_the_implementation_keeps_its_credentials_and_timeout(
    instance: api.Azathoth,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_TOKEN", "secret")
    exported = made(instance, authorization="SEARCH_TOKEN", timeout_seconds=12.0)

    (implementation,) = decode_tool_document(exported.text).implementations

    assert implementation.timeout_seconds == 12.0
    assert implementation.mcp is not None
    assert implementation.mcp.credentials.authorization == "SEARCH_TOKEN"


def test_a_document_not_yet_imported_is_named_without_a_revision() -> None:
    assert export_name("Search", kind="tool", revision=None, version="1.0.0") == (
        "search-1.0.0.tool.json"
    )


def test_the_server_is_named_once(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidArgumentError) as twice:
        made(instance, command=("search-server",))

    with pytest.raises(api.InvalidArgumentError) as neither:
        made(instance, url=None)

    assert str(twice.value) == SERVER_NAMED_TWICE_MESSAGE
    assert str(neither.value) == SERVER_NOT_NAMED_MESSAGE
    assert twice.value.code == "invalid_argument"


def test_an_implementation_that_cannot_be_declared_is_an_invalid_argument(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.InvalidArgumentError, match="must be an http or https URL"):
        made(instance, url="ftp://mcp.example.com")

    with pytest.raises(api.InvalidArgumentError, match=r"^tool: String should have"):
        made(instance, tool="")


def test_a_tool_the_server_does_not_serve_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError) as raised:
        made(instance, tool="nope")

    assert str(raised.value) == f"MCP server {URL} serves no tool named 'nope'."
    assert raised.value.code == "not_found"


def test_a_server_that_cannot_be_reached_is_unavailable(
    instance: api.Azathoth,
) -> None:
    def unreachable(
        connection: McpConnection,
    ) -> Any:
        raise ConnectionRefusedError("Connection refused")

    with pytest.raises(api.McpUnavailableError) as raised:
        made(instance, connect=unreachable)

    assert str(raised.value) == f"MCP server {URL} could not be listed: Connection refused"
    assert raised.value.code == "mcp_unavailable"


def test_an_authorization_variable_that_is_not_set_is_unavailable(
    instance: api.Azathoth,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEARCH_TOKEN", raising=False)

    with pytest.raises(api.McpUnavailableError, match="needs its authorization variable"):
        made(instance, authorization="SEARCH_TOKEN")


def test_a_closed_instance_makes_no_document(
    location: str,
) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        made(opened)

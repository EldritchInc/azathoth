"""Tests that the MCP guide shows what the server really does and says (ADR 0111)."""

import asyncio
import json
import re
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.persistence.repositories import open_repositories
from azathoth_mcp.access import READ_ALL_SCOPE, READ_SCOPE, McpCaller, Transport, invoke_scope
from azathoth_mcp.catalog import ToolCatalog, check_exposure
from azathoth_mcp.cli import NO_EXPOSURE_MESSAGE, build_parser
from azathoth_mcp.evidence import InvocationEvidence, RunEvidence, StepEvidence
from azathoth_mcp.exposure import ExposedWorkflow, ExposureDocumentError, decode_exposure
from azathoth_mcp.server import SERVER_NAME
from azathoth_mcp.service import (
    InvocationNotFoundError,
    ToolArgumentsError,
    ToolOutcome,
    ToolService,
)
from azathoth_mcp.web import UnprotectedBindError, require_protection

PROJECT_ROOT = Path(__file__).parents[2]

GUIDE = PROJECT_ROOT / "docs" / "mcp.md"

FENCE = re.compile(r"^```(?P<language>\S*)\n(?P<body>.*?)^```$", re.MULTILINE | re.DOTALL)


def text() -> str:
    """Return the guide."""

    return GUIDE.read_text(encoding="utf-8")


def section(
    heading: str,
) -> str:
    """Return one section of the guide, from its heading to the next of its level or above."""

    guide = text()
    start = guide.index(heading)
    level = heading.split(" ", 1)[0]
    following = re.search(rf"^#{{1,{len(level)}}} ", guide[start + len(heading) :], re.MULTILINE)

    return guide[start : start + len(heading) + following.start() if following else None]


def blocks(
    document: str,
    language: str,
) -> list[str]:
    """Return the bodies of every fenced block of one language in some text."""

    return [
        match.group("body")
        for match in FENCE.finditer(document)
        if match.group("language") == language
    ]


def exposure() -> dict[str, JsonValue]:
    """Return the guide's exposure document."""

    document = json.loads(blocks(section("## 3. Expose It"), "json")[0])

    assert isinstance(document, dict)

    return document


def service_without_production(
    tmp_path: Path,
) -> ToolService:
    """Return a service over the guide's document and a database with nothing promoted."""

    stores = open_repositories(tmp_path / "azathoth.db")

    return ToolService(
        catalog=ToolCatalog(decode_exposure(exposure()), stores.production_states),
        repositories=stores,
        load_runtime=lambda: pytest.fail("No runtime is needed."),
    )


def table_first_column(
    document: str,
) -> list[str]:
    """Return the first cell of every row of the Markdown tables in some text."""

    cells = [
        line.split("|")[1].strip()
        for line in document.splitlines()
        if line.startswith("| ") and not line.startswith("| ---")
    ]

    return [cell for cell in cells if cell not in ("Field", "Scope", "Option")]


def test_the_guide_is_one_of_the_user_guides() -> None:
    documents = (PROJECT_ROOT / "tests" / "test_docs.py").read_text(encoding="utf-8")

    assert '"docs/mcp.md",' in documents


def test_the_exposure_document_shown_is_valid() -> None:
    decoded = decode_exposure(exposure())

    assert [tool.name for tool in decoded.tools] == ["count_words"]
    assert decoded.tools[0].workflow_id == UUID("a1000000-0000-4000-8000-000000000002")


def test_the_example_workflow_promoted_is_the_one_exposed() -> None:
    promoted = section("## 2. Promote a Workflow")

    for block in (*blocks(promoted, "bash"), *blocks(promoted, "powershell")):
        assert "azathoth workflow promote a1000000-0000-4000-8000-000000000002" in block

    workflow = json.loads(
        (PROJECT_ROOT / "examples" / "workflows" / "word-count-messages.json").read_text(
            encoding="utf-8"
        )
    )

    assert workflow["metadata"]["id"] == "a1000000-0000-4000-8000-000000000002"


def test_every_field_of_an_entry_is_explained() -> None:
    assert table_first_column(section("## 3. Expose It")) == [
        f"`{name}`" for name in ExposedWorkflow.model_fields
    ]


def test_the_unpromoted_message_is_the_servers(
    tmp_path: Path,
) -> None:
    stores = open_repositories(tmp_path / "azathoth.db")

    with pytest.raises(ExposureDocumentError) as raised:
        check_exposure(decode_exposure(exposure()), stores.production_states)

    assert blocks(section("## 3. Expose It"), "text") == [f"{raised.value}\n"]


def test_the_claude_desktop_configurations_start_the_server_by_its_command() -> None:
    for heading, command in (
        ("### Claude Desktop on macOS", "/Users/you/azathoth/.venv/bin/azathoth-mcp"),
        (
            "### Claude Desktop on Windows",
            "C:\\Users\\you\\azathoth\\.venv\\Scripts\\azathoth-mcp.exe",
        ),
    ):
        (block,) = blocks(section(heading), "json")
        server = json.loads(block)["mcpServers"]["azathoth"]

        assert server["command"] == command
        assert server["args"][:2] == ["serve", "--exposure"]
        assert set(server["env"]) == {"AZATHOTH_DATABASE", "PATH"}
        folder = command.rsplit("\\" if "\\" in command else "/", 1)[0]

        assert server["env"]["PATH"].startswith(folder)


def test_the_outcome_shown_has_exactly_an_outcomes_fields() -> None:
    _, outcome = blocks(section("## 5. What a Call Returns"), "json")

    assert list(json.loads(outcome)) == list(ToolOutcome.model_fields)
    assert ToolOutcome.model_validate(json.loads(outcome)).is_error is False


def test_the_refused_arguments_message_is_the_servers(
    tmp_path: Path,
) -> None:
    service = service_without_production(tmp_path)
    caller = McpCaller(transport=Transport.STDIO)

    with pytest.raises(ToolArgumentsError) as raised:
        asyncio.run(service.invoke("count_words", {"input": 5}, caller=caller))

    assert blocks(section("## 5. What a Call Returns"), "text") == [f"{raised.value}\n"]


def test_the_evidence_shown_has_exactly_the_evidences_fields() -> None:
    request, evidence = blocks(section("## 6. Read an Invocation's Evidence"), "json")
    shown = json.loads(evidence)

    assert list(json.loads(request)) == ["invocation_id"]
    assert list(shown) == list(InvocationEvidence.model_fields)
    assert list(shown["run"]) == list(RunEvidence.model_fields)
    assert all(list(step) == list(StepEvidence.model_fields) for step in shown["run"]["steps"])
    assert InvocationEvidence.model_validate(shown).tool == "count_words"


def test_the_scopes_shown_are_the_servers() -> None:
    assert table_first_column(section("### Set Up the Identity Provider")) == [
        f"`{invoke_scope('<tool>')}`",
        f"`{READ_SCOPE}`",
        f"`{READ_ALL_SCOPE}`",
    ]


def test_the_http_options_shown_are_the_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["serve", "--help"])

    usage = capsys.readouterr().out
    shown = table_first_column(section("### Start the Server"))

    assert shown

    for cell in shown:
        option = cell.strip("`")

        assert f"{option}\n" in usage or f"{option} " in usage, cell


def test_the_not_found_message_is_the_servers(
    tmp_path: Path,
) -> None:
    service = service_without_production(tmp_path)
    shown = blocks(section("### What Clients See"), "text")
    invocation_id = re.search(r"[0-9a-f-]{36}", shown[0])

    assert invocation_id is not None

    reader = McpCaller(transport=Transport.HTTP, subject="bob", scopes=frozenset({READ_SCOPE}))

    with pytest.raises(InvocationNotFoundError) as raised:
        service.get_invocation({"invocation_id": invocation_id.group(0)}, caller=reader)

    assert shown == [f"{raised.value}\n"]


def test_the_loopback_refusal_is_the_servers() -> None:
    with pytest.raises(UnprotectedBindError) as raised:
        require_protection("0.0.0.0", None)

    assert blocks(section("### Try HTTP Without an Identity Provider"), "text") == [
        f"{raised.value}\n"
    ]


def test_the_missing_scope_message_is_the_servers() -> None:
    caller = McpCaller(transport=Transport.HTTP, subject="alice", scopes=frozenset())

    with pytest.raises(PermissionError) as raised:
        caller.require(invoke_scope("count_words"))

    assert blocks(section("## Troubleshooting"), "text") == [f"{raised.value}\n"]


def test_the_missing_document_message_is_the_servers() -> None:
    assert f"**`{NO_EXPOSURE_MESSAGE}`**" in section("## Troubleshooting")


def test_the_container_starts_the_server_through_tini() -> None:
    container = section("## 8. In the Container")

    for block in (*blocks(container, "bash"), *blocks(container, "powershell")):
        assert "--entrypoint /usr/bin/tini $IMAGE -- azathoth-mcp serve" in block


def test_the_server_is_named_as_the_configurations_name_it() -> None:
    assert SERVER_NAME == "azathoth"
    assert '"azathoth": {' in text()

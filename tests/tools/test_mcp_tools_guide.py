"""Tests that the guide to calling MCP tools shows what Azathoth really does (ADR 0119)."""

import asyncio
import importlib.util
import json
import os
import shlex
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from azathoth.cli import (
    WorkflowRunInput,
    build_parser,
    import_tool,
    import_workflow,
    run_workflow,
    tool_from_mcp,
)
from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.tools import McpCredentials, McpServer, ToolDocument, decode_tool_document
from azathoth.tools.mcp_document import mcp_tool_document, unpinned_implementation
from azathoth.tools.mcp_execution import (
    MCP_UNAVAILABLE_MESSAGE,
    McpConnection,
    McpToolExecutor,
)
from azathoth.workflows import ToolStepSpecification, decode_workflow_document

ROOT = Path(__file__).parents[2]

GUIDE = ROOT / "docs" / "mcp-tools.md"

SERVER_SCRIPT = ROOT / "examples" / "mcp" / "word_count_server.py"

WORKFLOW = ROOT / "examples" / "mcp" / "count-words-over-mcp.json"

COMMAND = ("python", "examples/mcp/word_count_server.py")

INPUT = "the old ones wait and dream"


def example_server() -> ModuleType:
    """Load the example server's module without running it."""

    spec = importlib.util.spec_from_file_location("word_count_server", SERVER_SCRIPT)

    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def in_process(
    connection: McpConnection,
) -> Any:
    """Connect to the example server in process."""

    return example_server().build_server()


def written() -> ToolDocument:
    """Return the document `tool from-mcp` writes for the example's tool."""

    unpinned = unpinned_implementation(
        server=McpServer(command=COMMAND), tool="count_words", credentials=McpCredentials()
    )
    listed = asyncio.run(
        McpToolExecutor(connect=in_process, environ={}, trace_context=dict).served_tool(
            unpinned.model_copy(update={"timeout_seconds": 30.0})
        )
    )

    assert listed is not None

    return mcp_tool_document(unpinned, listed)


def blocks(
    language: str,
) -> list[str]:
    """Return the guide's fenced blocks in one language."""

    text = GUIDE.read_text(encoding="utf-8")

    return [block.split("```", 1)[0] for block in text.split(f"```{language}\n")[1:]]


def test_the_guide_is_one_of_the_user_guides() -> None:
    documents = (ROOT / "tests" / "test_docs.py").read_text(encoding="utf-8")

    assert '"docs/mcp-tools.md",' in documents


def test_the_example_server_counts_words() -> None:
    implementation = written().implementations[0]
    executor = McpToolExecutor(connect=in_process, environ={}, trace_context=dict)

    assert asyncio.run(executor.execute(implementation, {"text": INPUT})) == {"count": 6}


def test_the_implementation_shown_is_the_one_written() -> None:
    (implementation, requirement) = (json.loads(block) for block in blocks("json"))

    assert implementation == written().implementations[0].model_dump(mode="json")
    assert requirement == {
        "requirement": {"name": "count_words", "version": "1.0.0", "runtime": "mcp"}
    }


def test_the_example_workflow_asks_for_the_written_tool() -> None:
    workflow = decode_workflow_document(WORKFLOW.read_text(encoding="utf-8"))
    (step,) = workflow.steps
    (_, shown) = (json.loads(block) for block in blocks("json"))
    document = written()

    assert isinstance(step.specification, ToolStepSpecification)
    assert step.specification.model_dump(mode="json") == shown
    assert step.specification.requirement.name == document.definition.name
    assert step.specification.requirement.version == document.definition.version
    assert str(workflow.metadata.id) in GUIDE.read_text(encoding="utf-8")


def test_the_guide_quotes_only_real_text() -> None:
    document = written()

    assert blocks("text") == [
        f"{MCP_UNAVAILABLE_MESSAGE}\n",
        f"Imported tool {document.definition.id}@1.0.0 revision 1.\n",
        "MCP tool <TOOL> on <SERVER> no longer matches its pinned schemas: pinned <PINNED>, "
        "served <SERVED>.\n",
    ]


@pytest.mark.parametrize("language", ["bash", "powershell"])
def test_every_azathoth_command_shown_parses(
    language: str,
) -> None:
    commands = [
        line.split(" > ", 1)[0]
        for block in blocks(language)
        for line in block.splitlines()
        if line.startswith("azathoth ")
    ]

    assert commands

    for command in commands:
        build_parser().parse_args(shlex.split(command)[1:])


def test_the_walkthrough_runs_against_the_real_server_over_stdio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("PATH", os.path.dirname(sys.executable) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("AZATHOTH_DATABASE", str(tmp_path / "azathoth.db"))

    assert tool_from_mcp(tool="count_words", command=COMMAND) == 0

    document = tmp_path / "count-words-mcp.json"
    document.write_text(capsys.readouterr().out, encoding="utf-8")

    assert decode_tool_document(document.read_text(encoding="utf-8")) == written()
    assert import_tool(document) == 0
    assert capsys.readouterr().out == (
        f"Imported tool {written().definition.id}@1.0.0 revision 1.\n"
    )
    assert import_workflow(WORKFLOW) == 0

    workflow = decode_workflow_document(WORKFLOW.read_text(encoding="utf-8"))
    capsys.readouterr()

    assert (
        run_workflow(
            workflow.metadata.id,
            workflow_input=WorkflowRunInput(payload=INPUT),
            output=WorkflowOutputFormat.RESULT,
        )
        == 0
    )
    assert capsys.readouterr().out == "6\n"

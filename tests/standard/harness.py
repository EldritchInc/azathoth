"""Run the standard tool library's documents the way a workflow step runs them."""

import asyncio
import re

import pytest
from pydantic import JsonValue

from azathoth.standard import standard_tool_documents
from azathoth.tools import (
    ProcessToolExecutor,
    ToolDocument,
    ToolExecutionError,
    ToolImplementation,
)

_FAILURE = re.compile(
    r"Tool implementation (?P<id>\S+) exited with status (?P<status>\d+): (?P<detail>.*)",
    re.DOTALL,
)


def standard_document(
    name: str,
) -> ToolDocument:
    """Return the standard document of one tool by name."""

    (document,) = (
        document for document in standard_tool_documents() if document.definition.name == name
    )

    return document


def standard_implementation(
    name: str,
) -> ToolImplementation:
    """Return the one implementation of a standard tool by name."""

    (implementation,) = standard_document(name).implementations

    return implementation


def run_standard_tool(
    name: str,
    inputs: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Run one standard tool through the process executor and return its output."""

    return asyncio.run(
        ProcessToolExecutor().execute(
            standard_implementation(name),
            inputs,
        )
    )


def standard_tool_failure(
    name: str,
    inputs: dict[str, JsonValue],
) -> tuple[int, str]:
    """Run one standard tool that must fail; return its exit status and its own message."""

    implementation = standard_implementation(name)

    with pytest.raises(ToolExecutionError) as error:
        run_standard_tool(name, inputs)

    match = _FAILURE.fullmatch(str(error.value))

    assert match is not None, str(error.value)
    assert match["id"] == str(implementation.id)

    return int(match["status"]), match["detail"]

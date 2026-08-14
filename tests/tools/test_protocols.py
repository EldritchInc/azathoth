"""Tests for tool execution protocols."""

import asyncio
from uuid import UUID

from pydantic import JsonValue

from azathoth.tools import ToolExecutor, ToolImplementation

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")


class RecordingToolExecutor:
    """Record tool executions for protocol verification."""

    def __init__(self) -> None:
        self.implementation: ToolImplementation | None = None
        self.inputs: dict[str, JsonValue] | None = None

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Record an execution and return deterministic output."""

        self.implementation = implementation
        self.inputs = inputs

        return {
            "count": 2,
        }


def create_implementation() -> ToolImplementation:
    """Create a deterministic tool implementation."""

    return ToolImplementation(
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime="python",
        source=(
            "def word_count(text: str) -> dict[str, int]:\n"
            "    return {'count': len(text.split())}\n"
        ),
    )


def execute_tool(
    executor: ToolExecutor,
    implementation: ToolImplementation,
) -> dict[str, JsonValue]:
    """Execute a tool through the executor protocol."""

    return asyncio.run(
        executor.execute(
            implementation,
            {
                "text": "hello world",
            },
        )
    )


def test_tool_executor_executes_implementation() -> None:
    executor = RecordingToolExecutor()
    implementation = create_implementation()

    result = execute_tool(
        executor,
        implementation,
    )

    assert result == {
        "count": 2,
    }
    assert executor.implementation == implementation
    assert executor.inputs == {
        "text": "hello world",
    }

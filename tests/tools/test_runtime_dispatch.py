"""Tests for dispatching tool implementations to their runtime executor."""

import asyncio
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.tools import (
    PYTHON_TOOL_RUNTIME,
    RuntimeToolExecutor,
    ToolImplementation,
    UnsupportedToolRuntimeError,
    default_tool_executors,
    supported_tool_runtimes,
    unsupported_runtime_message,
)

TOOL_ID = UUID("0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c01")

IMPLEMENTATION_ID = UUID("0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c11")

WORD_COUNT_SOURCE = "def run(text):\n    return {'count': len(text.split())}\n"


class RecordingExecutor:
    """Record every implementation executed and echo its runtime."""

    def __init__(self) -> None:
        self.calls: list[tuple[ToolImplementation, dict[str, JsonValue]]] = []

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Record the call and return the implementation runtime."""

        self.calls.append(
            (
                implementation,
                inputs,
            )
        )

        return {
            "runtime": implementation.runtime,
        }


def create_implementation(
    *,
    runtime: str,
) -> ToolImplementation:
    """Create one implementation for the given runtime."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=runtime,
        source=WORD_COUNT_SOURCE,
    )


def test_runtime_executor_dispatches_to_the_registered_runtime() -> None:
    first = RecordingExecutor()
    second = RecordingExecutor()

    result = asyncio.run(
        RuntimeToolExecutor(
            {
                "first": first,
                "second": second,
            }
        ).execute(
            create_implementation(
                runtime="second",
            ),
            {
                "text": "hello",
            },
        )
    )

    assert result == {
        "runtime": "second",
    }

    assert first.calls == []

    assert second.calls == [
        (
            create_implementation(
                runtime="second",
            ),
            {
                "text": "hello",
            },
        )
    ]


def test_runtime_executor_rejects_an_unregistered_runtime() -> None:
    with pytest.raises(
        UnsupportedToolRuntimeError,
        match="^No tool executor supports runtime 'javascript'.$",
    ):
        asyncio.run(
            RuntimeToolExecutor(
                {
                    "first": RecordingExecutor(),
                }
            ).execute(
                create_implementation(
                    runtime="javascript",
                ),
                {},
            )
        )


def test_runtime_executor_reports_supported_runtimes() -> None:
    executor = RuntimeToolExecutor(
        {
            "second": RecordingExecutor(),
            "first": RecordingExecutor(),
        }
    )

    assert executor.runtimes == (
        "first",
        "second",
    )

    assert executor.supports("first")
    assert not executor.supports("third")


def test_default_runtime_executor_executes_python_tools() -> None:
    result = asyncio.run(
        RuntimeToolExecutor().execute(
            create_implementation(
                runtime=PYTHON_TOOL_RUNTIME,
            ),
            {
                "text": "one two three",
            },
        )
    )

    assert result == {
        "count": 3,
    }


def test_default_runtime_executor_rejects_unknown_runtimes() -> None:
    with pytest.raises(
        UnsupportedToolRuntimeError,
        match="^No tool executor supports runtime 'wasm'.$",
    ):
        asyncio.run(
            RuntimeToolExecutor().execute(
                create_implementation(
                    runtime="wasm",
                ),
                {},
            )
        )


def test_default_tool_executors_are_fresh_per_call() -> None:
    assert default_tool_executors() is not default_tool_executors()


def test_supported_tool_runtimes_include_python() -> None:
    assert PYTHON_TOOL_RUNTIME in supported_tool_runtimes()

    assert supported_tool_runtimes() == tuple(sorted(supported_tool_runtimes()))


def test_unsupported_runtime_message_names_implementation_and_runtimes() -> None:
    assert unsupported_runtime_message(
        create_implementation(
            runtime="javascript",
        )
    ) == (
        f"Tool implementation {IMPLEMENTATION_ID} uses unsupported runtime 'javascript'; "
        f"supported runtimes: {', '.join(supported_tool_runtimes())}."
    )

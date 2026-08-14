"""Tests for Python tool execution."""

import asyncio
from uuid import UUID

import pytest

from azathoth.tools import (
    PythonToolExecutor,
    ToolEntrypointError,
    ToolExecutionError,
    ToolImplementation,
    UnsupportedToolRuntimeError,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")


def create_implementation(
    *,
    runtime: str = "python",
    entrypoint: str = "run",
    source: str | None = None,
) -> ToolImplementation:
    """Create a deterministic executable tool implementation."""

    if source is None:
        source = "def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"

    return ToolImplementation(
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=runtime,
        entrypoint=entrypoint,
        source=source,
    )


def test_python_tool_executor_executes_tool() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation()

    result = asyncio.run(
        executor.execute(
            implementation,
            {
                "text": "hello world",
            },
        )
    )

    assert result == {
        "count": 2,
    }


def test_python_tool_executor_passes_multiple_inputs() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        source=(
            "def run(first: int, second: int) -> dict[str, int]:\n"
            "    return {'total': first + second}\n"
        ),
    )

    result = asyncio.run(
        executor.execute(
            implementation,
            {
                "first": 2,
                "second": 3,
            },
        )
    )

    assert result == {
        "total": 5,
    }


def test_python_tool_executor_uses_custom_entrypoint() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        entrypoint="word_count",
        source=(
            "def word_count(text: str) -> dict[str, int]:\n"
            "    return {'count': len(text.split())}\n"
        ),
    )

    result = asyncio.run(
        executor.execute(
            implementation,
            {
                "text": "hello world",
            },
        )
    )

    assert result == {
        "count": 2,
    }


def test_python_tool_executor_supports_async_entrypoint() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        source=(
            "async def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"
        ),
    )

    result = asyncio.run(
        executor.execute(
            implementation,
            {
                "text": "hello world",
            },
        )
    )

    assert result == {
        "count": 2,
    }


def test_python_tool_executor_rejects_unsupported_runtime() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        runtime="javascript",
    )

    with pytest.raises(
        UnsupportedToolRuntimeError,
        match="only supports the 'python' runtime",
    ):
        asyncio.run(
            executor.execute(
                implementation,
                {},
            )
        )


def test_python_tool_executor_rejects_missing_entrypoint() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        entrypoint="missing",
    )

    with pytest.raises(
        ToolEntrypointError,
        match="'missing' was not found",
    ):
        asyncio.run(
            executor.execute(
                implementation,
                {},
            )
        )


def test_python_tool_executor_rejects_non_callable_entrypoint() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        source="run = 42\n",
    )

    with pytest.raises(
        ToolEntrypointError,
        match="'run' is not callable",
    ):
        asyncio.run(
            executor.execute(
                implementation,
                {},
            )
        )


def test_python_tool_executor_reports_invalid_source() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        source="def run(:\n",
    )

    with pytest.raises(
        ToolExecutionError,
        match="could not be loaded",
    ):
        asyncio.run(
            executor.execute(
                implementation,
                {},
            )
        )


def test_python_tool_executor_reports_execution_failure() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        source=("def run() -> dict[str, int]:\n    return {'value': 1 // 0}\n"),
    )

    with pytest.raises(
        ToolExecutionError,
        match="failed during execution",
    ):
        asyncio.run(
            executor.execute(
                implementation,
                {},
            )
        )


def test_python_tool_executor_rejects_non_object_output() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        source=("def run() -> int:\n    return 42\n"),
    )

    with pytest.raises(
        ToolExecutionError,
        match="produced invalid output",
    ):
        asyncio.run(
            executor.execute(
                implementation,
                {},
            )
        )


def test_python_tool_executor_does_not_expose_import_builtin() -> None:
    executor = PythonToolExecutor()
    implementation = create_implementation(
        source=("import os\n\ndef run() -> dict[str, str]:\n    return {'cwd': os.getcwd()}\n"),
    )

    with pytest.raises(
        ToolExecutionError,
        match="could not be loaded",
    ):
        asyncio.run(
            executor.execute(
                implementation,
                {},
            )
        )

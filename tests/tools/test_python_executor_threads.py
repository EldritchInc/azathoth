"""Tests for running synchronous Python tools off the event loop."""

import asyncio
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.tools import (
    PythonToolExecutor,
    ToolExecutionError,
    ToolImplementation,
)

TOOL_ID = UUID("1b2c3d4e-5f6a-4b7c-9d8e-0f1a2b3c4d01")

IMPLEMENTATION_ID = UUID("1b2c3d4e-5f6a-4b7c-9d8e-0f1a2b3c4d11")

SYNC_SOURCE = "def run(text):\n    return {'count': len(text.split())}\n"

ASYNC_SOURCE = "async def run(text):\n    return {'count': len(text.split())}\n"

FAILING_SOURCE = "def run(text):\n    return {'count': 1 // 0}\n"


class ThreadRecorder:
    """Record every function handed to asyncio.to_thread, then delegate."""

    def __init__(self) -> None:
        self._delegate = asyncio.to_thread
        self.functions: list[Callable[..., Any]] = []

    async def __call__(
        self,
        function: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Record the function and run it in a worker thread."""

        self.functions.append(function)

        return await self._delegate(
            function,
            *args,
            **kwargs,
        )


def create_implementation(
    source: str,
) -> ToolImplementation:
    """Create one Python implementation with the given source."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime="python",
        source=source,
    )


def execute(
    source: str,
) -> dict[str, JsonValue]:
    """Execute one implementation counting the words of a fixed text."""

    return asyncio.run(
        PythonToolExecutor().execute(
            create_implementation(source),
            {
                "text": "one two three",
            },
        )
    )


def install_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> ThreadRecorder:
    """Replace asyncio.to_thread, which the Python executor looks up per call."""

    recorder = ThreadRecorder()

    monkeypatch.setattr(
        asyncio,
        "to_thread",
        recorder,
    )

    return recorder


def test_sync_entrypoint_runs_in_a_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = install_recorder(monkeypatch)

    assert execute(SYNC_SOURCE) == {
        "count": 3,
    }

    assert len(recorder.functions) == 1
    assert getattr(recorder.functions[0], "__name__", None) == "run"


def test_async_entrypoint_is_awaited_on_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = install_recorder(monkeypatch)

    assert execute(ASYNC_SOURCE) == {
        "count": 3,
    }

    assert recorder.functions == []


def test_sync_entrypoint_failure_in_a_thread_is_wrapped() -> None:
    with pytest.raises(
        ToolExecutionError,
        match=f"^Tool implementation {IMPLEMENTATION_ID} failed during execution.$",
    ):
        execute(FAILING_SOURCE)


def test_concurrent_sync_tools_each_produce_their_own_output() -> None:
    async def execute_both() -> list[dict[str, JsonValue]]:
        executor = PythonToolExecutor()
        implementation = create_implementation(SYNC_SOURCE)

        results = await asyncio.gather(
            executor.execute(
                implementation,
                {
                    "text": "one",
                },
            ),
            executor.execute(
                implementation,
                {
                    "text": "one two",
                },
            ),
        )

        return list(results)

    assert asyncio.run(execute_both()) == [
        {
            "count": 1,
        },
        {
            "count": 2,
        },
    ]

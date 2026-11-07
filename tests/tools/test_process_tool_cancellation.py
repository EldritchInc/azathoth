"""Tests that a cancelled process tool is stopped and waited for on every Python.

On a Python without gh-119710, backported to CPython's 3.13 branch in July
2026, `Process.wait()` returns only once every pipe of the process has
closed. A tool cancelled
before `communicate()` wrote its inputs kept its stdin pipe open, so waiting
for it after killing it never returned, and a command stopped by SIGTERM
could hang there. The executor closes stdin before it waits.
"""

import asyncio
import sys
from uuid import UUID

import pytest

from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    ProcessToolExecutor,
    ToolImplementation,
)

TOOL_ID = UUID("3d4e5f6a-7b8c-4d9e-9fa0-2b3c4d5e6f02")

IMPLEMENTATION_ID = UUID("3d4e5f6a-7b8c-4d9e-9fa0-2b3c4d5e6f12")

SLEEPING = ToolImplementation(
    id=IMPLEMENTATION_ID,
    tool_id=TOOL_ID,
    tool_version="1.0.0",
    runtime=PROCESS_TOOL_RUNTIME,
    source="import json, sys, time\njson.load(sys.stdin)\ntime.sleep(60)\n",
    command=(sys.executable,),
    timeout_seconds=120.0,
)
"""A tool that reads its inputs, then sleeps far longer than any test waits."""


def test_a_tool_cancelled_before_it_reads_its_inputs_has_stdin_closed_before_the_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[asyncio.subprocess.Process] = []
    stdin_closed_at_wait: list[bool] = []
    start = ProcessToolExecutor._start

    async def starting_then_cancelled(
        implementation: ToolImplementation,
        arguments: tuple[str, ...],
    ) -> asyncio.subprocess.Process:
        """Start the tool, then cancel its step before its inputs are written."""

        process = await start(implementation, arguments)
        wait = process.wait

        async def recording_wait() -> int:
            stdin = process.stdin
            stdin_closed_at_wait.append(stdin is not None and stdin.is_closing())

            return await wait()

        monkeypatch.setattr(process, "wait", recording_wait)
        started.append(process)

        task = asyncio.current_task()

        assert task is not None

        task.cancel()

        return process

    monkeypatch.setattr(ProcessToolExecutor, "_start", staticmethod(starting_then_cancelled))

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ProcessToolExecutor().execute(SLEEPING, {"text": "never read"}))

    (process,) = started

    assert stdin_closed_at_wait == [True]
    assert process.returncode is not None
    assert process.returncode != 0


def test_a_tool_cancelled_while_it_runs_is_killed_and_waited_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[asyncio.subprocess.Process] = []
    start = ProcessToolExecutor._start

    async def recording(
        implementation: ToolImplementation,
        arguments: tuple[str, ...],
    ) -> asyncio.subprocess.Process:
        """Start the tool, and keep its process."""

        process = await start(implementation, arguments)
        started.append(process)

        return process

    monkeypatch.setattr(ProcessToolExecutor, "_start", staticmethod(recording))

    async def cancel_while_sleeping() -> None:
        task = asyncio.create_task(
            ProcessToolExecutor().execute(SLEEPING, {"text": "read, then sleep"})
        )
        deadline = asyncio.get_running_loop().time() + 30

        while not started:
            assert not task.done(), task
            assert asyncio.get_running_loop().time() < deadline, "the tool never started"
            await asyncio.sleep(0.01)

        await asyncio.sleep(0.2)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=30)

    asyncio.run(cancel_while_sleeping())

    (process,) = started

    assert process.returncode is not None
    assert process.returncode != 0
    assert process.stdin is not None
    assert process.stdin.is_closing()

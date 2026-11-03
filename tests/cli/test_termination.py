"""Tests that an interrupted or terminated command releases its run and exits as a shell expects."""

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import application, main
from azathoth.cli.termination import (
    INTERRUPTED_MESSAGE,
    INTERRUPTED_STATUS,
    TERMINATED_MESSAGE,
    TERMINATED_STATUS,
    CommandTerminated,
    terminating_on_sigterm,
)
from azathoth.persistence.repositories import open_repositories
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE

PROJECT_ROOT = Path(__file__).parents[2]

CLI_README = PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md"

SLEEP_TOOL_ID = "c1600000-0000-4000-8000-000000000001"

SLEEP_WORKFLOW_ID = "c1600000-0000-4000-8000-000000000011"

SLEEP_STEP_ID = "c1600000-0000-4000-8000-000000000021"


# The statuses and messages


def test_an_interrupted_command_exits_130_and_a_terminated_one_143() -> None:
    assert (INTERRUPTED_STATUS, TERMINATED_STATUS) == (130, 143)
    assert (INTERRUPTED_MESSAGE, TERMINATED_MESSAGE) == ("Interrupted.", "Terminated.")


def test_termination_is_a_system_exit_no_except_exception_catches() -> None:
    terminated = CommandTerminated()

    assert isinstance(terminated, SystemExit)
    assert not isinstance(terminated, Exception)
    assert terminated.code == 143


@pytest.mark.parametrize(
    ("raised", "status", "message"),
    [
        pytest.param(KeyboardInterrupt(), 130, "Interrupted.\n", id="ctrl-c"),
        pytest.param(CommandTerminated(), 143, "Terminated.\n", id="sigterm"),
    ],
)
def test_main_reports_a_stopped_command_on_stderr_alone(
    raised: BaseException,
    status: int,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def stop(*_: object) -> int:
        raise raised

    monkeypatch.setattr(application, "_dispatch", stop)

    assert main(["workflow", "list"]) == status

    captured = capsys.readouterr()

    assert (captured.out, captured.err) == ("", message)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX delivers SIGTERM to a handler.")
def test_sigterm_inside_the_block_raises_termination_and_the_handler_is_restored() -> None:
    before = signal.getsignal(signal.SIGTERM)

    with pytest.raises(CommandTerminated), terminating_on_sigterm():
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(5)

    assert signal.getsignal(signal.SIGTERM) == before


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX delivers SIGTERM to a handler.")
def test_sigterm_inside_an_event_loop_cancels_its_tasks_so_they_clean_up() -> None:
    cleaned: list[str] = []

    async def work() -> None:
        async def child() -> None:
            try:
                await asyncio.sleep(30)
            finally:
                cleaned.append("child")

        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(child())
                await asyncio.sleep(0.05)
                os.kill(os.getpid(), signal.SIGTERM)
                await asyncio.sleep(30)
        finally:
            cleaned.append("parent")

    with pytest.raises(CommandTerminated), terminating_on_sigterm():
        asyncio.run(work())

    assert sorted(cleaned) == ["child", "parent"]


def test_a_cancellation_that_is_not_termination_is_left_alone() -> None:
    async def cancelled() -> None:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError), terminating_on_sigterm():
        asyncio.run(cancelled())


def test_outside_the_main_thread_nothing_is_installed() -> None:
    seen: list[object] = []

    def install() -> None:
        with terminating_on_sigterm():
            seen.append(signal.getsignal(signal.SIGTERM))

    before = signal.getsignal(signal.SIGTERM)

    thread = threading.Thread(target=install)
    thread.start()
    thread.join()

    assert seen == [before]


def test_the_cli_readme_quotes_the_statuses_and_messages() -> None:
    text = CLI_README.read_text(encoding="utf-8")

    assert f"```text\n{INTERRUPTED_MESSAGE}\n```" in text
    assert f"```text\n{TERMINATED_MESSAGE}\n```" in text
    assert "status 130" in text
    assert "status 143" in text


# A real command, stopped while its run executes


SLEEP_SOURCE = (
    "import json\nimport sys\nimport time\n\n"
    "inputs = json.load(sys.stdin)\ntime.sleep(60)\n"
    "json.dump({'text': inputs['text']}, sys.stdout)\n"
)
"""A tool that sleeps far longer than any test waits."""


def sleep_tool(
    source: str = SLEEP_SOURCE,
) -> dict[str, object]:
    """Return a process tool that runs the given source, by default sleeping a minute."""

    return {
        "definition": {
            "id": SLEEP_TOOL_ID,
            "name": "sleep_awhile",
            "description": "Sleep, then echo the text.",
            "version": "1.0.0",
            "input_schema": {
                "json_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                }
            },
            "output_schema": {
                "json_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                }
            },
        },
        "implementations": [
            {
                "id": "c1600000-0000-4000-8000-000000000002",
                "tool_id": SLEEP_TOOL_ID,
                "tool_version": "1.0.0",
                "version": "1.0.0",
                "runtime": "process",
                "entrypoint": "run",
                "source": source,
                "command": ["python"],
                "timeout_seconds": 120.0,
            }
        ],
        "test_cases": [],
    }


def sleep_workflow() -> dict[str, object]:
    """Return a workflow of one step that runs the sleeping tool."""

    return {
        "metadata": {
            "id": SLEEP_WORKFLOW_ID,
            "name": "sleep awhile",
            "description": "Run one step that sleeps.",
            "version": "1.0.0",
        },
        "steps": [
            {
                "id": SLEEP_STEP_ID,
                "specification": {
                    "requirement": {
                        "name": "sleep_awhile",
                        "version": "1.0.0",
                        "runtime": "process",
                    }
                },
                "depends_on": [],
                "inputs": [
                    {
                        "name": "text",
                        "source": {
                            "event_type": "workflow.input.received",
                            "field_name": "input",
                        },
                    }
                ],
                "outputs": [{"name": "text", "path": ["text"]}],
                "conditions": [],
                "retry_policy": {
                    "max_attempts": 1,
                    "initial_delay_seconds": 0.0,
                    "backoff_multiplier": 1.0,
                    "maximum_delay_seconds": None,
                },
                "failure_policy": "fail_workflow",
            }
        ],
        "result": {"name": "text"},
    }


@pytest.fixture
def sleeping_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Import the sleeping tool and workflow into a fresh database, and return it."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(database))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)

    tool = tmp_path / "sleep-tool.json"
    tool.write_text(json.dumps(sleep_tool()), encoding="utf-8")
    workflow = tmp_path / "sleep-workflow.json"
    workflow.write_text(json.dumps(sleep_workflow()), encoding="utf-8")

    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "kind": "invoke",
                "version": 1,
                "idempotency_key": "terminated-1",
                "workflow_id": SLEEP_WORKFLOW_ID,
                "input": {"value": "the old ones wait"},
            }
        ),
        encoding="utf-8",
    )

    for arguments in (
        ("tool", "import", str(tool)),
        ("workflow", "import", str(workflow)),
        ("workflow", "promote", SLEEP_WORKFLOW_ID),
    ):
        status = main(arguments)
        captured = capsys.readouterr()

        assert status == 0, captured.err

    return database


def started_runs(
    database: Path,
) -> list[UUID]:
    """Return the runs whose journal shows an attempt under way."""

    journal = open_repositories(database).run_journal
    repositories = open_repositories(database)

    with repositories.database.transaction() as session:
        rows = session.fetchall("SELECT DISTINCT run_id FROM run_journal ORDER BY run_id")

    return [
        UUID(str(row[0]))
        for row in rows
        if any(
            entry.event.type == "attempt.started" for entry in journal.entries(UUID(str(row[0])))
        )
    ]


COMMANDS = {
    "run": ("workflow", "run", SLEEP_WORKFLOW_ID, "--input", '"the old ones wait"'),
    "invoke": ("workflow", "invoke", SLEEP_WORKFLOW_ID, "--input", '"the old ones wait"'),
    "job": ("job", "run", "request.json"),
}


@pytest.mark.skipif(sys.platform == "win32", reason="Signals are POSIX-only here.")
@pytest.mark.parametrize("command", sorted(COMMANDS))
@pytest.mark.parametrize(
    ("sent", "status", "message"),
    [
        pytest.param(signal.SIGTERM, 143, "Terminated.\n", id="sigterm"),
        pytest.param(signal.SIGINT, 130, "Interrupted.\n", id="sigint"),
    ],
)
def test_a_stopped_command_releases_its_run_and_leaves_its_journal_unfinished(
    sleeping_workflow: Path,
    command: str,
    sent: signal.Signals,
    status: int,
    message: str,
) -> None:
    #
    # With faulthandler on, a child that never stops can be made to print
    # every thread's stack, so a hang says where it is.
    #
    child = subprocess.Popen(
        [sys.executable, "-X", "faulthandler", "-m", "azathoth.cli", *COMMANDS[command]],
        cwd=sleeping_workflow.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "AZATHOTH_DATABASE": str(sleeping_workflow)},
    )

    try:
        deadline = time.monotonic() + 30

        while not started_runs(sleeping_workflow):
            assert child.poll() is None, child.communicate()
            assert time.monotonic() < deadline, "the run never started its step"
            time.sleep(0.05)

        (run_id,) = started_runs(sleeping_workflow)
        repositories = open_repositories(sleeping_workflow)

        assert repositories.run_leases.get(run_id) is not None

        child.send_signal(sent)

        try:
            out, err = child.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            child.send_signal(signal.SIGABRT)
            _, stacks = child.communicate(timeout=30)

            raise AssertionError(
                f"azathoth {command} did not stop within 30 seconds of {sent.name}; "
                f"its threads were:\n{stacks}"
            ) from None
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()

    assert child.returncode == status
    assert out == ""
    assert err == message
    assert repositories.run_leases.get(run_id) is None
    assert repositories.runs.get(run_id) is None
    assert "run.finished" not in [
        entry.event.type for entry in repositories.run_journal.entries(run_id)
    ]

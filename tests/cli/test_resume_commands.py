"""Tests that interrupted runs and invocations resume from the command line (ADR 0105).

A real `azathoth` process is stopped with SIGTERM while its one step runs,
which leaves the run unfinished and its lease released. The step's tool
sleeps only the first time it runs, so the resume finishes at once.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import main
from azathoth.cli.rendering import render_resume_lines
from azathoth.persistence.repositories import open_repositories
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from tests.cli.test_termination import (
    SLEEP_WORKFLOW_ID,
    sleep_tool,
    sleep_workflow,
    started_runs,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="The run is interrupted with SIGTERM, which only POSIX delivers to a handler.",
)

ONCE_SOURCE = (
    "import json\nimport os\nimport sys\nimport time\n\n"
    "inputs = json.load(sys.stdin)\n"
    "marker = inputs['text']\n"
    "if not os.path.exists(marker):\n"
    "    open(marker, 'w').close()\n"
    "    time.sleep(60)\n"
    "json.dump({'text': 'resumed'}, sys.stdout)\n"
)
"""A tool that sleeps the first time it runs, and returns at once after."""

CLI_README = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"


def cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one command in this process, returning its status, stdout and stderr."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Import and promote the sleep-once workflow into a fresh database, and return it."""

    path = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)

    tool = tmp_path / "once-tool.json"
    tool.write_text(json.dumps(sleep_tool(ONCE_SOURCE)), encoding="utf-8")
    workflow = tmp_path / "once-workflow.json"
    workflow.write_text(json.dumps(sleep_workflow()), encoding="utf-8")

    for arguments in (
        ("tool", "import", str(tool)),
        ("workflow", "import", str(workflow)),
        ("workflow", "promote", SLEEP_WORKFLOW_ID),
    ):
        status, _, err = cli(capsys, *arguments)

        assert status == 0, err

    return path


def marker(
    database: Path,
) -> str:
    """Return the input of the run: the file the tool leaves the first time."""

    return str(database.parent / "slept")


def interrupted(
    database: Path,
    *arguments: str,
) -> UUID:
    """Start a command in a real process, stop it with SIGTERM mid-step, and return its run."""

    child = subprocess.Popen(
        [sys.executable, "-m", "azathoth.cli", *arguments],
        cwd=database.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "AZATHOTH_DATABASE": str(database)},
    )

    try:
        deadline = time.monotonic() + 30

        while not started_runs(database) or not Path(marker(database)).exists():
            assert child.poll() is None, child.communicate()
            assert time.monotonic() < deadline, "the run never started its step"
            time.sleep(0.05)

        child.send_signal(signal.SIGTERM)
        _, err = child.communicate(timeout=30)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()

    assert (child.returncode, err) == (143, "Terminated.\n")

    (run_id,) = started_runs(database)

    return run_id


# Configured runs


def test_an_interrupted_run_is_shown_unfinished_and_resumes_under_its_id(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = interrupted(
        database, "workflow", "run", SLEEP_WORKFLOW_ID, "--input", json.dumps(marker(database))
    )

    assert cli(capsys, "run", "show", str(run_id)) == (
        1,
        "",
        f"Run {run_id} has not finished; resume it with azathoth run resume {run_id}.\n",
    )

    status, out, err = cli(capsys, "run", "resume", str(run_id), "--output", "text")

    assert (status, err) == (0, "")
    assert f"Run ID: {run_id}\nResumed: 1 time\nStatus: succeeded\n" in out

    run = open_repositories(database).runs.get(run_id)

    assert run is not None
    assert run.succeeded
    assert run.steps[0].attempts[0].attempt_number == 1

    status, out, _ = cli(capsys, "run", "show", str(run_id))

    assert status == 0
    assert "Resumed: 1 time\n" in out

    assert cli(capsys, "run", "resume", str(run_id)) == (
        1,
        "",
        f"Run {run_id} has already finished.\n",
    )


def test_a_resumed_run_reports_its_result_as_workflow_run_would(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = interrupted(
        database, "workflow", "run", SLEEP_WORKFLOW_ID, "--input", json.dumps(marker(database))
    )

    assert cli(capsys, "run", "resume", str(run_id), "--output", "result") == (
        0,
        '"resumed"\n',
        "",
    )


def test_a_run_another_process_still_holds_is_not_resumed(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = interrupted(
        database, "workflow", "run", SLEEP_WORKFLOW_ID, "--input", json.dumps(marker(database))
    )

    #
    # As if the process had been killed outright: its lease is still live.
    #
    now = datetime.now(UTC)
    open_repositories(database).run_leases.acquire(
        run_id,
        holder="killed-process",
        now=now,
        duration=timedelta(seconds=60),
    )
    expires = (now + timedelta(seconds=60)).isoformat(timespec="seconds")

    assert cli(capsys, "run", "resume", str(run_id)) == (
        1,
        "",
        f"Run {run_id} is still running (its lease expires at {expires}).\n",
    )
    assert open_repositories(database).runs.get(run_id) is None


def test_a_run_never_journaled_cannot_be_resumed(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = UUID("c1800000-0000-4000-8000-000000000001")

    assert cli(capsys, "run", "resume", str(run_id)) == (
        1,
        "",
        f"Run {run_id} has no journal to resume.\n",
    )
    assert cli(capsys, "run", "show", str(run_id)) == (1, "", f"Run {run_id} was not found.\n")


# Production invocations


def test_an_interrupted_invocation_resumes_to_its_result(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = interrupted(
        database,
        "workflow",
        "invoke",
        SLEEP_WORKFLOW_ID,
        "--input",
        json.dumps(marker(database)),
    )

    (invocation,) = open_repositories(database).invocations.invocations()

    status, out, _ = cli(capsys, "invocation", "show", str(invocation.id))

    assert status == 0
    assert f"Outcome: pending\nRun ID: {run_id}\n" in out
    assert "Resumed:" not in out

    assert cli(capsys, "run", "show", str(run_id)) == (
        1,
        "",
        f"Run {run_id} has not finished; resume it with "
        f"azathoth invocation resume {invocation.id}.\n",
    )
    assert cli(capsys, "run", "resume", str(run_id)) == (
        1,
        "",
        f"Run {run_id} executes invocation {invocation.id}; resume it with "
        f"azathoth invocation resume {invocation.id}.\n",
    )

    resumed = cli(capsys, "invocation", "resume", str(invocation.id), "--output", "result")

    #
    # The tool has slept once already, so a fresh invocation finishes at once
    # and shows what the resumed one should have reported.
    #
    fresh = cli(
        capsys,
        "workflow",
        "invoke",
        SLEEP_WORKFLOW_ID,
        "--input",
        json.dumps(marker(database)),
        "--output",
        "result",
    )

    assert resumed == fresh
    assert resumed[0] == 0

    result = open_repositories(database).invocations.result(invocation.id)

    assert result is not None
    assert result.model_dump(mode="json")["invocation_id"] == str(invocation.id)

    association = open_repositories(database).invocation_runs.get(invocation.id)

    assert association is not None
    assert association.run_id == run_id

    status, out, _ = cli(capsys, "invocation", "show", str(invocation.id))

    assert status == 0
    assert f"Outcome: succeeded\nRun ID: {run_id}\nResumed: 1 time\n" in out

    assert cli(capsys, "invocation", "resume", str(invocation.id)) == (
        1,
        "",
        f"Invocation {invocation.id} has already completed.\n",
    )


def test_an_unknown_invocation_cannot_be_resumed(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation_id = UUID("c1800000-0000-4000-8000-000000000002")

    assert cli(capsys, "invocation", "resume", str(invocation_id)) == (
        1,
        "",
        f"Invocation {invocation_id} was not found.\n",
    )


# Jobs


def job_request(
    database: Path,
) -> Path:
    """Write the job request for the sleep-once workflow, and return its path."""

    request = database.parent / "request.json"
    request.write_text(
        json.dumps(
            {
                "kind": "invoke",
                "version": 1,
                "idempotency_key": "resume-1",
                "workflow_id": SLEEP_WORKFLOW_ID,
                "input": {"value": marker(database)},
            }
        ),
        encoding="utf-8",
    )

    return request


def test_a_job_whose_run_is_still_held_reports_it_incomplete(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = job_request(database)
    run_id = interrupted(database, "job", "run", str(request))

    open_repositories(database).run_leases.acquire(
        run_id,
        holder="killed-process",
        now=datetime.now(UTC),
        duration=timedelta(seconds=60),
    )

    status, out, _ = cli(capsys, "job", "run", str(request))
    envelope = json.loads(out)

    assert status == 1
    assert envelope["status"] == "incomplete"
    assert envelope["replayed"] is True
    assert envelope["error"]["code"] == "invocation_incomplete"


def test_a_job_retried_after_its_run_was_stopped_resumes_it(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = job_request(database)
    run_id = interrupted(database, "job", "run", str(request))

    (invocation,) = open_repositories(database).invocations.invocations()

    status, out, err = cli(capsys, "job", "run", str(request))
    envelope = json.loads(out)

    assert (status, err) == (0, "")
    assert envelope["status"] == "succeeded"
    assert envelope["invocation_id"] == str(invocation.id)
    assert envelope["replayed"] is False

    association = open_repositories(database).invocation_runs.get(invocation.id)

    assert association is not None
    assert association.run_id == run_id

    #
    # Once it has a result, the key replays it like any other.
    #
    status, out, _ = cli(capsys, "job", "run", str(request))

    assert status == 0
    assert json.loads(out) == {**envelope, "replayed": True}


# Rendering and documentation


@pytest.mark.parametrize(
    ("resumes", "lines"),
    [(0, ()), (1, ("Resumed: 1 time",)), (3, ("Resumed: 3 times",))],
)
def test_a_run_names_how_often_it_was_resumed(
    resumes: int,
    lines: tuple[str, ...],
) -> None:
    assert render_resume_lines(resumes) == lines


def test_the_cli_readme_documents_the_resume_commands() -> None:
    text = CLI_README.read_text(encoding="utf-8")

    for line in (
        "azathoth run resume <RUN_ID>",
        "azathoth invocation resume <INVOCATION_ID>",
        "Run <RUN_ID> has not finished; resume it with azathoth run resume <RUN_ID>.",
        "Run <RUN_ID> has not finished; resume it with azathoth invocation resume <INVOCATION_ID>.",
        "Run <RUN_ID> executes invocation <INVOCATION_ID>; resume it with azathoth "
        "invocation resume <INVOCATION_ID>.",
        "Run <RUN_ID> has already finished.",
        "Invocation <INVOCATION_ID> has already completed.",
        "Resumed: 1 time",
    ):
        assert f"\n{line}\n" in text, line

"""A loop killed halfway resumes without running its finished iterations again (ADR 0105).

A real `azathoth workflow run` of the countdown loop is stopped with SIGTERM
once a few of its children have finished. Resuming the parent replays the
children it already ran, under their iteration keys, finishes the one it
was running, and runs the rest: every iteration runs exactly once.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import main
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import journal_resumes
from tests.examples.test_loop_workflow_examples import (
    COUNTDOWN_WORKFLOW_ID,
    LOOP_WORKFLOW_ID,
    configure_loop_walkthrough,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="The loop is interrupted with SIGTERM, which only POSIX delivers to a handler.",
)

LOOP_STEP_ID = UUID("a1000000-0000-4000-8000-000000000051")

ITERATIONS = 6

FINISHED_BEFORE_STOPPING = 2


def finished_children(
    database: Path,
) -> int:
    """Return how many child invocations have their result."""

    repositories = open_repositories(database)

    return sum(
        1
        for invocation in repositories.invocations.invocations()
        if repositories.invocations.result(invocation.id) is not None
    )


def loop_run_id(
    database: Path,
) -> UUID:
    """Return the loop's one run, found by its journal."""

    repositories = open_repositories(database)

    with repositories.database.transaction() as session:
        rows = session.fetchall(
            "SELECT run_id FROM run_journal WHERE position = 1 AND workflow_id = ?",
            (str(LOOP_WORKFLOW_ID),),
        )

    (row,) = rows

    return UUID(str(row[0]))


def test_a_loop_stopped_halfway_resumes_and_runs_every_iteration_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_loop_walkthrough(monkeypatch, tmp_path, capsys)

    parent = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "azathoth.cli",
            "workflow",
            "run",
            str(LOOP_WORKFLOW_ID),
            "--input",
            f'{{"remaining": {ITERATIONS}}}',
            "--output",
            "result",
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(os.environ),
    )

    try:
        deadline = time.monotonic() + 120

        while finished_children(database) < FINISHED_BEFORE_STOPPING:
            assert parent.poll() is None, parent.communicate()
            assert time.monotonic() < deadline, "the loop never ran its first children"
            time.sleep(0.05)

        parent.send_signal(signal.SIGTERM)
        _, err = parent.communicate(timeout=60)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.communicate()

    assert (parent.returncode, err) == (143, "Terminated.\n")

    run_id = loop_run_id(database)
    stopped_after = finished_children(database)

    assert FINISHED_BEFORE_STOPPING <= stopped_after < ITERATIONS
    assert open_repositories(database).runs.get(run_id) is None

    status = main(("run", "resume", str(run_id), "--output", "result"))
    captured = capsys.readouterr()

    assert (status, captured.out, captured.err) == (0, "[6, 5, 4, 3, 2, 1]\n", "")

    repositories = open_repositories(database)
    invocations = repositories.invocations.invocations()
    keys = sorted(
        invocation.idempotency.key for invocation in invocations if invocation.idempotency
    )

    assert keys == sorted(
        f"azathoth:{run_id}:{LOOP_STEP_ID}:1:{iteration}" for iteration in range(1, ITERATIONS + 1)
    )
    assert len(invocations) == ITERATIONS
    assert len(repositories.runs.runs_for_workflow(COUNTDOWN_WORKFLOW_ID)) == ITERATIONS
    assert len(repositories.run_children.children_of(run_id)) == ITERATIONS
    assert journal_resumes(repositories.run_journal.entries(run_id)) == 1

    loop = repositories.runs.get(run_id)

    assert loop is not None
    assert loop.succeeded
    assert {value.name: value.value for value in loop.steps[0].values} == {
        "items": [6, 5, 4, 3, 2, 1],
        "iterations": ITERATIONS,
        "completed": True,
    }

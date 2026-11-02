"""A map stopped halfway resumes, and every item runs exactly once (ADR 0105, ADR 0106).

A real `azathoth workflow run` of a mapping parent is stopped while its
children run. SIGTERM releases the parent's lease; SIGKILL leaves it live,
so the test marks it lapsed, as a minute's wait would, and resumes at once
while the children the killed parent started are still running. Every probe
item tallies each execution, so running an item twice cannot go unnoticed.
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
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import journal_resumes
from tests.standard.test_map_workflow import (
    CHILD_WORKFLOW_ID,
    MAP_STEP_ID,
    PARENT_WORKFLOW_ID,
    deploy_probe,
    echoed,
    import_document,
    overlap,
    parent_workflow,
    settings,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="The map is interrupted with signals, which only POSIX delivers this way.",
)


def finished_items(
    path: Path,
) -> int:
    """Return how many child invocations have their result."""

    repositories = open_repositories(path)

    return sum(
        1
        for invocation in repositories.invocations.invocations()
        if repositories.invocations.result(invocation.id) is not None
    )


def parent_run_id(
    path: Path,
) -> UUID:
    """Return the mapping parent's one run, found by its journal."""

    with open_repositories(path).database.transaction() as session:
        (row,) = session.fetchall(
            "SELECT run_id FROM run_journal WHERE position = 1 AND workflow_id = ?",
            (PARENT_WORKFLOW_ID,),
        )

    return UUID(str(row[0]))


def interrupt(
    path: Path,
    items: list[dict[str, object]],
    *,
    sent: signal.Signals,
    after: int,
) -> tuple[UUID, int]:
    """Run the parent in a real process, stop it once `after` items finish; return its run."""

    parent = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "azathoth.cli",
            "workflow",
            "run",
            PARENT_WORKFLOW_ID,
            "--input",
            json.dumps(items),
            "--output",
            "result",
        ],
        cwd=path.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(os.environ),
    )

    try:
        deadline = time.monotonic() + 120

        while finished_items(path) < after:
            assert parent.poll() is None, parent.communicate()
            assert time.monotonic() < deadline, "the map never finished its first items"
            time.sleep(0.05)

        parent.send_signal(sent)
        parent.communicate(timeout=60)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.communicate()

    return parent_run_id(path), parent.returncode


def resume(
    capsys: pytest.CaptureFixture[str],
    run_id: UUID,
) -> tuple[int, str, str]:
    """Resume the parent in this process, returning its status, stdout and stderr."""

    status = main(("run", "resume", str(run_id), "--output", "result"))
    captured = capsys.readouterr()

    return status, captured.out, captured.err


def tallies(
    tally: Path,
    count: int,
) -> list[int]:
    """Return how many times each item's probe ran."""

    return [
        len((tally / f"{index}.tally").read_text().splitlines())
        if (tally / f"{index}.tally").exists()
        else 0
        for index in range(count)
    ]


def assert_every_item_ran_once(
    path: Path,
    run_id: UUID,
    count: int,
) -> None:
    """Check the map's children: one invocation and one run per item, under its key."""

    repositories = open_repositories(path)
    invocations = repositories.invocations.invocations()

    assert sorted(
        invocation.idempotency.key for invocation in invocations if invocation.idempotency
    ) == sorted(f"azathoth:{run_id}:{MAP_STEP_ID}:1:{index}" for index in range(count))
    assert len(invocations) == count
    assert len(repositories.runs.runs_for_workflow(UUID(CHILD_WORKFLOW_ID))) == count
    assert len(repositories.run_children.children_of(run_id)) == count
    assert journal_resumes(repositories.run_journal.entries(run_id)) == 1


@pytest.fixture
def mapping(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Deploy the probe child, and import a parent mapping it two at a time."""

    database = deploy_probe(monkeypatch, tmp_path, capsys)

    import_document(capsys, tmp_path, "workflow", parent_workflow(settings(max_concurrency=2)))

    return database


def test_a_map_stopped_with_sigterm_resumes_and_runs_every_item_once(
    mapping: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tally = tmp_path / "tally"
    probe = tmp_path / "probe"
    tally.mkdir()
    probe.mkdir()

    items: list[dict[str, object]] = [
        {"value": index, "sleep": 1.0, "tally": str(tally), "probe": str(probe)}
        for index in range(6)
    ]

    run_id, status = interrupt(mapping, items, sent=signal.SIGTERM, after=2)

    assert status == 143
    assert finished_items(mapping) < 6
    assert open_repositories(mapping).run_leases.get(run_id) is None

    status, out, err = resume(capsys, run_id)

    assert (status, err) == (0, "")
    assert json.loads(out) == echoed(*range(6))
    assert tallies(tally, 6) == [1] * 6
    assert_every_item_ran_once(mapping, run_id, 6)

    #
    # The children the stopped parent left running, and the ones the
    # resumed parent started, never ran more than two at a time.
    #
    assert overlap(probe, 6) <= 2


def test_a_map_killed_outright_resumes_while_its_children_still_run(
    mapping: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tally = tmp_path / "tally"
    tally.mkdir()

    items: list[dict[str, object]] = [
        {"value": index, "sleep": 2.0, "tally": str(tally)} for index in range(4)
    ]

    run_id, status = interrupt(mapping, items, sent=signal.SIGKILL, after=1)

    assert status == -signal.SIGKILL

    #
    # The killed parent's lease is still live, so a resume now is refused.
    #
    status, _, err = resume(capsys, run_id)

    assert status == 1
    assert err.startswith(f"Run {run_id} is still running (its lease expires at ")

    #
    # Mark the lease lapsed, as waiting out its minute would, and resume
    # while children the killed parent started are still running.
    #
    with open_repositories(mapping).database.transaction() as session:
        session.execute(
            "UPDATE run_leases SET expires_at = ? WHERE run_id = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), str(run_id)),
        )

    assert finished_items(mapping) < 4

    status, out, err = resume(capsys, run_id)

    assert (status, err) == (0, "")
    assert json.loads(out) == echoed(*range(4))
    assert tallies(tally, 4) == [1] * 4
    assert_every_item_ran_once(mapping, run_id, 4)


def test_an_item_that_failed_before_the_stop_fails_the_resumed_map_without_running_again(
    mapping: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tally = tmp_path / "tally"
    tally.mkdir()

    items: list[dict[str, object]] = [
        {"value": 0, "fail": True, "tally": str(tally)},
        {"value": 1, "sleep": 2.0, "tally": str(tally)},
        {"value": 2, "sleep": 2.0, "tally": str(tally)},
    ]

    run_id, status = interrupt(mapping, items, sent=signal.SIGTERM, after=1)

    assert status == 143

    status, out, err = resume(capsys, run_id)

    assert (status, out) == (1, "")
    assert f"Item 0 of 3: child workflow {CHILD_WORKFLOW_ID} invocation " in err
    assert "(1 of 3 items failed)." in err
    assert tallies(tally, 3) == [1, 1, 1]

    parent = open_repositories(mapping).runs.get(run_id)

    assert parent is not None
    assert parent.halted

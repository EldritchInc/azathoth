"""Tests that the commands that run workflows journal their runs while they execute (ADR 0105)."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import application, main
from azathoth.persistence.repositories import open_repositories
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from azathoth.workflows import (
    RunJournalError,
    RunLeaseLostError,
    RunResumeError,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowRunRepository,
    WorkflowRun,
)
from tests.cli.test_lineage_commands import cli
from tests.examples.test_run_workflow_examples import (
    PARENT_WORKFLOW_ID,
    child_call,
    configure_child_walkthrough,
)
from tests.examples.test_word_count_benchmark_examples import run_cli
from tests.examples.test_word_count_messages_examples import (
    WORKFLOW_ID as CHILD_WORKFLOW_ID,
)
from tests.workflows.test_runner_journal import rebuilt


@pytest.fixture
def walkthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Import the child-workflow walkthrough and promote its child; return the database."""

    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)

    configure_child_walkthrough(monkeypatch, tmp_path, capsys)

    run_cli(capsys, "workflow", "promote", str(CHILD_WORKFLOW_ID))

    return tmp_path / "azathoth.db"


def journaled_run(
    database: Path,
    run: WorkflowRun,
) -> WorkflowRun:
    """Return the run rebuilt from its journal, checking the journal is whole."""

    entries = open_repositories(database).run_journal.entries(run.id)

    assert [entry.position for entry in entries] == list(range(1, len(entries) + 1))
    assert entries[0].event.type == "run.started"
    assert entries[-1].event.type == "run.finished"

    return rebuilt(entries)


def invoked_run(
    database: Path,
) -> tuple[WorkflowRun, UUID]:
    """Return the child workflow's one invocation's run, and the invocation's ID."""

    (invocation,) = SQLiteProductionInvocationRepository(database).invocations_for_workflow(
        CHILD_WORKFLOW_ID
    )
    association = SQLiteProductionInvocationRunRepository(database).get(invocation.id)

    assert association is not None

    run = SQLiteWorkflowRunRepository(database).get(association.run_id)

    assert run is not None

    return run, invocation.id


def test_workflow_run_journals_its_run_with_no_invocation(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, _ = cli(
        capsys, "workflow", "run", str(CHILD_WORKFLOW_ID), "--input", '"a b"', "--output", "result"
    )

    assert status == 0

    (run,) = SQLiteWorkflowRunRepository(walkthrough).runs_for_workflow(CHILD_WORKFLOW_ID)

    assert journaled_run(walkthrough, run) == run
    assert {
        entry.invocation_id for entry in open_repositories(walkthrough).run_journal.entries(run.id)
    } == {None}


def test_workflow_invoke_journals_its_run_under_the_invocation(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, _ = cli(
        capsys,
        "workflow",
        "invoke",
        str(CHILD_WORKFLOW_ID),
        "--input",
        '"a b"',
        "--output",
        "result",
    )

    assert status == 0

    run, invocation_id = invoked_run(walkthrough)
    journal = open_repositories(walkthrough).run_journal

    assert journaled_run(walkthrough, run) == run
    assert journal.invocation_run_id(invocation_id) == run.id
    assert {entry.invocation_id for entry in journal.entries(run.id)} == {invocation_id}


def test_job_run_journals_its_run_under_the_invocation(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "kind": "invoke",
                "version": 1,
                "idempotency_key": "journal-1",
                "workflow_id": str(CHILD_WORKFLOW_ID),
                "input": {"value": "a b"},
            }
        ),
        encoding="utf-8",
    )

    status, out, _ = cli(capsys, "job", "run", str(request))

    assert status == 0
    assert json.loads(out)["status"] == "succeeded"

    run, invocation_id = invoked_run(walkthrough)

    assert journaled_run(walkthrough, run) == run
    assert open_repositories(walkthrough).run_journal.invocation_run_id(invocation_id) == run.id


def test_a_parent_and_the_child_its_tool_invokes_each_journal_their_own_run(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, _ = cli(
        capsys,
        "workflow",
        "run",
        str(PARENT_WORKFLOW_ID),
        "--input",
        child_call(CHILD_WORKFLOW_ID, "the old ones wait"),
        "--output",
        "result",
    )

    assert status == 0

    (parent,) = SQLiteWorkflowRunRepository(walkthrough).runs_for_workflow(PARENT_WORKFLOW_ID)
    child, _ = invoked_run(walkthrough)

    assert journaled_run(walkthrough, parent) == parent
    assert journaled_run(walkthrough, child) == child


@pytest.mark.parametrize(
    "raised",
    [
        pytest.param(RunJournalError("Run 1 already records journal position 2."), id="journal"),
        pytest.param(RunLeaseLostError.taken_over(UUID(int=1)), id="lost"),
        pytest.param(RunResumeError(UUID(int=1), "Run 1 has no journal to resume."), id="resume"),
    ],
)
def test_a_run_that_stops_unfinished_is_reported_in_one_line(
    raised: Exception,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def stop(*_: object) -> int:
        raise raised

    monkeypatch.setattr(application, "_dispatch", stop)

    assert main(["workflow", "list"]) == 1
    assert capsys.readouterr().err == f"{raised}\n"

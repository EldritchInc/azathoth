"""Tests of `workflow invoke --idempotency-key`, and the keys composition tools pass (ADR 0105)."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import main
from azathoth.cli.keyed_invocation import keyed_request
from azathoth.jobs import job_request_digest
from azathoth.persistence.repositories import open_repositories
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from tests.cli.test_lineage_commands import PARENT_STEP_ID
from tests.examples.test_loop_workflow_examples import (
    LOOP_WORKFLOW_ID,
    configure_loop_walkthrough,
)
from tests.examples.test_run_workflow_examples import (
    PARENT_WORKFLOW_ID,
    child_call,
    configure_child_walkthrough,
)
from tests.examples.test_word_count_benchmark_examples import run_cli
from tests.examples.test_word_count_messages_examples import (
    WORKFLOW_ID as CHILD_WORKFLOW_ID,
)

LOOP_STEP_ID = UUID("a1000000-0000-4000-8000-000000000051")

CLI_README = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"


def cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one command, returning its status, stdout and stderr."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


@pytest.fixture
def walkthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Import the child-workflow walkthrough and promote its child; return the database."""

    configure_child_walkthrough(monkeypatch, tmp_path, capsys)
    run_cli(capsys, "workflow", "promote", str(CHILD_WORKFLOW_ID))

    return tmp_path / "azathoth.db"


def keyed(
    capsys: pytest.CaptureFixture[str],
    text: str,
    *,
    key: str = "order-4711",
    output: str = "jsonl",
) -> tuple[int, str, str]:
    """Invoke the child workflow under a key."""

    return cli(
        capsys,
        "workflow",
        "invoke",
        str(CHILD_WORKFLOW_ID),
        "--input",
        json.dumps(text),
        "--idempotency-key",
        key,
        "--output",
        output,
    )


def last_record(
    out: str,
) -> dict[str, object]:
    """Return the final JSON Lines record of a command's output."""

    record: dict[str, object] = json.loads(out.splitlines()[-1])

    return record


# The key


def test_a_keyed_invocation_records_its_key_and_reports_as_any_invocation(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out, err = keyed(capsys, "the old ones wait", output="result")

    assert (status, err) == (0, "")
    assert json.loads(out) == {"result": 4}

    (invocation,) = open_repositories(walkthrough).invocations.invocations()

    assert invocation.idempotency is not None
    assert invocation.idempotency.key == "order-4711"
    assert invocation.idempotency.request_digest == job_request_digest(
        keyed_request(
            workflow_id=CHILD_WORKFLOW_ID,
            payload="the old ones wait",
            idempotency_key="order-4711",
        )
    )


def test_the_same_request_under_the_same_key_replays_without_running_again(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = keyed(capsys, "the old ones wait", output="result")
    again = keyed(capsys, "the old ones wait", output="result")

    assert again == first

    repositories = open_repositories(walkthrough)

    assert len(repositories.invocations.invocations()) == 1
    assert len(repositories.runs.runs_for_workflow(CHILD_WORKFLOW_ID)) == 1


def test_a_replay_ends_its_json_lines_with_the_recorded_result(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = last_record(keyed(capsys, "the old ones wait")[1])
    status, out, _ = keyed(capsys, "the old ones wait")

    assert status == 0
    assert last_record(out) == first


@pytest.mark.parametrize("output", ["jsonl", "result"])
def test_another_request_under_a_used_key_is_a_conflict(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
    output: str,
) -> None:
    keyed(capsys, "the old ones wait")

    status, out, err = keyed(capsys, "something else entirely", output=output)

    assert status == 1

    if output == "jsonl":
        record = last_record(out)

        assert record["type"] == "error"
        assert record["code"] == "idempotency_conflict"
    else:
        assert out == ""
        assert "order-4711" in err

    assert len(open_repositories(walkthrough).invocations.invocations()) == 1


def test_a_conflict_in_text_says_why_on_stderr(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keyed(capsys, "the old ones wait")

    status, out, err = keyed(capsys, "something else entirely", output="text")

    assert (status, out) == (1, "")
    assert err.endswith("\n")
    assert "order-4711" in err


def test_a_key_that_is_not_one_is_refused_by_the_parser(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        keyed(capsys, "the old ones wait", key="")

    assert raised.value.code == 2
    assert "An idempotency key must not be empty." in capsys.readouterr().err


# The keys the composition tools pass


def test_run_workflow_invokes_its_child_under_its_step_attempts_key(
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

    repositories = open_repositories(walkthrough)
    (parent,) = repositories.runs.runs_for_workflow(PARENT_WORKFLOW_ID)
    (child,) = repositories.invocations.invocations()

    assert child.idempotency is not None
    assert child.idempotency.key == f"azathoth:{parent.id}:{PARENT_STEP_ID}:1"

    (indexed,) = repositories.run_children.children_of(parent.id)

    assert indexed.child_invocation_id == child.id
    assert (indexed.parent_step_id, indexed.parent_attempt) == (PARENT_STEP_ID, 1)


def test_loop_workflow_invokes_each_iteration_under_its_own_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_loop_walkthrough(monkeypatch, tmp_path, capsys)

    status, out, _ = cli(
        capsys,
        "workflow",
        "run",
        str(LOOP_WORKFLOW_ID),
        "--input",
        '{"remaining": 3}',
        "--output",
        "result",
    )

    assert (status, out) == (0, "[3, 2, 1]\n")

    repositories = open_repositories(database)
    (parent,) = repositories.runs.runs_for_workflow(LOOP_WORKFLOW_ID)

    keys = [
        invocation.idempotency.key if invocation.idempotency is not None else None
        for invocation in repositories.invocations.invocations()
    ]

    assert keys == [f"azathoth:{parent.id}:{LOOP_STEP_ID}:1:{iteration}" for iteration in (1, 2, 3)]
    assert len(repositories.run_children.children_of(parent.id)) == 3


def test_a_child_invoked_outside_any_step_has_no_key(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)

    assert (
        cli(
            capsys,
            "workflow",
            "invoke",
            str(CHILD_WORKFLOW_ID),
            "--input",
            '"the old ones wait"',
            "--output",
            "result",
        )[0]
        == 0
    )

    (invocation,) = open_repositories(walkthrough).invocations.invocations()

    assert invocation.idempotency is None


# The children of a run


def test_run_children_lists_what_a_runs_steps_started(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli(
        capsys,
        "workflow",
        "run",
        str(PARENT_WORKFLOW_ID),
        "--input",
        child_call(CHILD_WORKFLOW_ID, "the old ones wait"),
        "--output",
        "result",
    )

    repositories = open_repositories(walkthrough)
    (parent,) = repositories.runs.runs_for_workflow(PARENT_WORKFLOW_ID)
    (child,) = repositories.invocations.invocations()
    (child_run,) = repositories.runs.runs_for_workflow(CHILD_WORKFLOW_ID)

    assert cli(capsys, "run", "children", str(parent.id)) == (
        0,
        f"Child Run ID: {child_run.id}\n"
        f"Workflow ID: {CHILD_WORKFLOW_ID}\n"
        f"Invocation ID: {child.id}\n"
        f"Parent Step ID: {PARENT_STEP_ID} (attempt 1)\n"
        "Status: succeeded\n",
        "",
    )

    status, out, _ = cli(capsys, "run", "show", str(parent.id))

    assert status == 0
    assert "\nChildren: 1\n" in out

    assert cli(capsys, "run", "children", str(child_run.id)) == (
        0,
        f"Run {child_run.id} started no children.\n",
        "",
    )


def test_the_children_of_a_run_that_does_not_exist_are_not_found(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_id = UUID("c1900000-0000-4000-8000-0000000000ff")

    assert cli(capsys, "run", "children", str(run_id)) == (
        1,
        "",
        f"Run {run_id} was not found.\n",
    )


def test_the_cli_readme_documents_keys_and_children() -> None:
    text = CLI_README.read_text(encoding="utf-8")

    for line in (
        "azathoth workflow invoke <WORKFLOW_ID> --input <JSON> --idempotency-key <KEY>",
        "azathoth run children <RUN_ID>",
        "Child Run ID: <RUN_ID>",
        "Run <RUN_ID> started no children.",
        "Children: 2",
    ):
        assert f"\n{line}\n" in text, line

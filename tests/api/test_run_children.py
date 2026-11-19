"""Contract tests for the runs a run's steps started, through the service API (ADR 0129)."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from tests.api.test_models import parses
from tests.cli.test_keyed_invocation import cli, walkthrough
from tests.cli.test_lineage_commands import PARENT_STEP_ID
from tests.examples.test_run_workflow_examples import PARENT_WORKFLOW_ID, child_call
from tests.examples.test_word_count_messages_examples import WORKFLOW_ID as CHILD_WORKFLOW_ID

__all__ = ["walkthrough"]

UNKNOWN = UUID("c1900000-0000-4000-8000-0000000000ff")


def parent_and_child(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[UUID, UUID, UUID]:
    """Run the parent workflow; return its run's, its child run's and the invocation's IDs."""

    status, _, err = cli(
        capsys,
        "workflow",
        "run",
        str(PARENT_WORKFLOW_ID),
        "--input",
        child_call(CHILD_WORKFLOW_ID, "the old ones wait"),
        "--output",
        "result",
    )

    assert status == 0, err

    repositories = open_repositories(walkthrough)
    (parent,) = repositories.runs.runs_for_workflow(PARENT_WORKFLOW_ID)
    (child_run,) = repositories.runs.runs_for_workflow(CHILD_WORKFLOW_ID)
    (invocation,) = repositories.invocations.invocations()

    return parent.id, child_run.id, invocation.id


def test_a_runs_children_are_listed_with_where_they_started_and_how_they_ended(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parent_id, child_id, invocation_id = parent_and_child(walkthrough, capsys)

    with api.open(walkthrough) as instance:
        (child,) = instance.runs.children(parent_id)

    assert child.child_run_id == child_id
    assert child.child_workflow_id == CHILD_WORKFLOW_ID
    assert child.child_invocation_id == invocation_id
    assert child.parent_run_id == parent_id
    assert (child.parent_step_id, child.parent_attempt) == (PARENT_STEP_ID, 1)
    assert child.depth == 1
    assert child.status == "succeeded"
    assert child.command == f"azathoth run show {child_id}"
    assert parses(child.command)


def test_a_run_that_started_nothing_has_no_children(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, child_id, _ = parent_and_child(walkthrough, capsys)

    with api.open(walkthrough) as instance:
        assert instance.runs.children(child_id) == ()


def test_a_child_with_no_finished_run_is_unfinished_and_has_no_command(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parent_id, _, _ = parent_and_child(walkthrough, capsys)
    repositories = open_repositories(walkthrough)
    (indexed,) = repositories.run_children.children_of(parent_id)
    started = indexed.model_copy(
        update={"child_run_id": uuid4(), "recorded_at": indexed.recorded_at.replace(year=2100)}
    )

    repositories.run_children.record(started)

    with api.open(walkthrough) as instance:
        children = instance.runs.children(parent_id)

    assert [child.child_run_id for child in children][-1] == started.child_run_id
    assert (children[-1].status, children[-1].command) == ("unfinished", None)


def test_a_parent_that_never_finished_lists_the_children_it_started(
    walkthrough: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parent_id, child_id, _ = parent_and_child(walkthrough, capsys)
    repositories = open_repositories(walkthrough)
    (indexed,) = repositories.run_children.children_of(parent_id)
    unfinished_parent = uuid4()

    repositories.run_children.record(
        indexed.model_copy(update={"parent_run_id": unfinished_parent, "child_run_id": uuid4()})
    )

    with api.open(walkthrough) as instance:
        (child,) = instance.runs.children(unfinished_parent)

    assert child.parent_run_id == unfinished_parent
    assert child.child_run_id != child_id


def test_a_run_neither_kept_nor_journaled_is_not_found(
    walkthrough: Path,
) -> None:
    with api.open(walkthrough) as instance, pytest.raises(api.NotFoundError) as refused:
        instance.runs.children(UNKNOWN)

    assert str(refused.value) == f"Run {UNKNOWN} was not found."

"""Contract tests for exporting a run's citations through the service API (ADR 0129)."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth import api
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import create_production_invocation, journaled_citations
from tests.api.test_models import parses
from tests.cli.test_citation_annotations import database, invoked, run
from tests.cli.test_cited_invocation import CITED_STEP_ID, WORKFLOW_ID

__all__ = ["database"]

UNKNOWN = UUID("c16f0000-0000-4000-8000-000000000001")


def test_a_runs_annotations_are_the_collection_the_command_line_prints(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, run_id = invoked(database, capsys)
    _, printed, _ = run("run", "annotations", str(run_id), capsys=capsys)

    with api.open(database) as instance:
        annotations = instance.runs.annotations(run_id)

    assert annotations.subject_id == run_id
    assert annotations.run_id == run_id
    assert annotations.collection == json.loads(printed)
    assert annotations.items == tuple(json.loads(printed)["first"]["items"])
    assert len(annotations.items) == 1
    assert annotations.command == f"azathoth run annotations {run_id}"
    assert parses(annotations.command)


def test_an_invocations_annotations_are_its_runs(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation_id, run_id = invoked(database, capsys)

    with api.open(database) as instance:
        by_invocation = instance.invocations.annotations(invocation_id)
        by_run = instance.runs.annotations(run_id)

    assert by_invocation.subject_id == invocation_id
    assert by_invocation.run_id == run_id
    assert by_invocation.collection == by_run.collection
    assert by_invocation.command == f"azathoth invocation annotations {invocation_id}"
    assert parses(by_invocation.command)


def test_an_unknown_run_or_invocation_is_not_found(
    database: Path,
) -> None:
    with api.open(database) as instance:
        with pytest.raises(api.NotFoundError) as by_run:
            instance.runs.annotations(UNKNOWN)

        with pytest.raises(api.NotFoundError) as by_invocation:
            instance.invocations.annotations(UNKNOWN)

    assert str(by_run.value) == f"Run {UNKNOWN} was not found."
    assert str(by_invocation.value) == f"Invocation {UNKNOWN} was not found."


def test_an_invocation_with_no_run_has_no_annotations(
    database: Path,
) -> None:
    invocation = create_production_invocation(workflow_id=UUID(WORKFLOW_ID), payload=None)

    open_repositories(database).invocations.save(invocation)

    with api.open(database) as instance, pytest.raises(api.NotFoundError) as refused:
        instance.invocations.annotations(invocation.id)

    assert str(refused.value) == f"Invocation {invocation.id} has no run."


def test_a_record_the_content_store_no_longer_holds_is_content_unavailable(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, run_id = invoked(database, capsys)
    ((_, digest),) = journaled_citations(open_repositories(database).run_journal, run_id)

    monkeypatch.setattr(
        "azathoth.api.annotations.stored_citation_checks",
        lambda store, digest: None,
    )

    with api.open(database) as instance, pytest.raises(api.ContentUnavailableError) as refused:
        instance.runs.annotations(run_id)

    assert refused.value.code == "content_unavailable"
    assert str(refused.value) == (
        f"Citation record {digest} of step {CITED_STEP_ID} is not in the content store."
    )


def test_a_run_with_no_cited_step_has_an_empty_collection(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, run_id = invoked(database, capsys)

    monkeypatch.setattr("azathoth.api.annotations.journaled_citations", lambda journal, run: ())

    with api.open(database) as instance:
        annotations = instance.runs.annotations(run_id)

    assert annotations.items == ()
    assert annotations.collection["total"] == 0

"""Tests that the production commands say the same here and on a remote (ADR 0140).

`workflow production`, `workflow revisions`, `workflow invocations`,
`invocation show`, `workflow promote` and `workflow rollback` given
`--remote` read or change production through that remote's service API,
and print what they print here. Each reading command is run over one
database twice, once here and once on a remote serving it.
"""

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.cli import main
from azathoth.cli.parsing.targets import NOT_YET_ON_A_REMOTE
from azathoth.cli.rendering import RecordedCitations, render_production_invocation
from azathoth.cli.rendering.production_views import render_invocation_detail
from azathoth.context import Context, LineageRun, LineageStep, WorkflowLineage, create_lineage_event
from azathoth.providers import ModelPortfolioEntry, SQLiteModelPortfolioRepository
from azathoth.revisions import Author
from azathoth.workflows import (
    InvocationIdempotency,
    ProductionInvocationSuccess,
    SQLiteProductionInvocationRepository,
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    WorkflowProductionRevision,
    create_production_invocation,
    describe_value_reference,
)
from tests.api.test_invoke import promote
from tests.api.test_runs import COUNT_WORKFLOW_ID, stock
from tests.cli import test_production_inspection_commands as inspection
from tests.cli.test_remote_option import Reaching
from tests.remote.test_call_routes import ERIS, Served

URL = "http://remote.test"

TOKEN_VARIABLE = "AZATHOTH_ORIGIN_TOKEN"

AUTHOR = Author(name="Eris Discordia", email="eris@example.com")

KEYED_INVOCATION_ID = UUID("c1400000-0000-4000-8000-0000000000c1")


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the command line at a database with production history, naming `origin` its remote."""

    configured = inspection.configure_database(monkeypatch, tmp_path)
    configured.touch()
    workflows = SQLiteWorkflowRepository(configured)
    workflows.save(inspection.create_workflow("third-model"))
    workflows.save(inspection.create_workflow(workflow_id=inspection.OTHER_WORKFLOW_ID))

    revisions = SQLiteWorkflowProductionRevisionRepository(configured)
    states = SQLiteWorkflowProductionStateRepository(configured)
    first = WorkflowProductionRevision(
        id=inspection.FIRST_REVISION_ID,
        state=inspection.create_state("first-model"),
        created_at=inspection.CREATED_AT,
    )
    emitting = inspection.create_state("second-model")
    second = WorkflowProductionRevision(
        id=inspection.SECOND_REVISION_ID,
        state=emitting,
        created_at=inspection.CREATED_AT + timedelta(minutes=5),
        author=AUTHOR,
        restores=inspection.FIRST_REVISION_ID,
    )
    revisions.save(first)
    revisions.save(second)
    states.set(emitting)

    inspection.save_invocation_history(configured)
    keyed = inspection.save_invocation(
        configured,
        "keyed",
        created_at=inspection.CREATED_AT + timedelta(minutes=15),
    )
    lineage = create_lineage_event(
        WorkflowLineage(
            depth=1,
            parent=LineageStep(
                workflow_id=inspection.WORKFLOW_ID,
                run_id=inspection.FIRST_RUN_ID,
                step_id=inspection.STEP_ID,
                attempt=1,
            ),
            root=LineageRun(workflow_id=inspection.WORKFLOW_ID, run_id=inspection.FIRST_RUN_ID),
        )
    )
    invocations = SQLiteProductionInvocationRepository(configured)
    invocations.save(
        keyed.model_copy(
            update={
                "id": KEYED_INVOCATION_ID,
                "idempotency": InvocationIdempotency(
                    key="order-412",
                    request_digest="d" * 64,
                ),
                "initial_context": Context(
                    events=(*keyed.initial_context.events, lineage),
                ),
            }
        )
    )
    invocations.save_result(
        ProductionInvocationSuccess(invocation_id=KEYED_INVOCATION_ID, result="OK")
    )

    with api.open(configured) as instance:
        instance.remotes.add("origin", URL, token_variable=TOKEN_VARIABLE)

    monkeypatch.setenv(TOKEN_VARIABLE, "azr_origin")
    monkeypatch.setattr(httpx, "Client", Reaching(Served(configured, principal=ERIS)))

    return configured


def said(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    status = main(arguments)
    printed = capsys.readouterr()

    return status, printed.out, printed.err


def invocation_ids(
    path: Path,
) -> list[UUID]:
    with api.open(path) as instance:
        return [
            invocation.invocation_id
            for invocation in instance.invocations.list(inspection.WORKFLOW_ID)
        ]


def test_each_production_reading_command_says_the_same_here_and_on_a_remote(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = str(inspection.WORKFLOW_ID)
    unknown = str(inspection.UNKNOWN_WORKFLOW_ID)
    commands = [
        ("workflow", "production", workflow),
        ("workflow", "production", str(inspection.OTHER_WORKFLOW_ID)),
        ("workflow", "production", unknown),
        ("workflow", "revisions", workflow),
        ("workflow", "revisions", workflow, "--limit", "1"),
        ("workflow", "revisions", str(inspection.OTHER_WORKFLOW_ID)),
        ("workflow", "revisions", unknown),
        ("workflow", "invocations", workflow),
        ("workflow", "invocations", workflow, "--limit", "2"),
        ("workflow", "invocations", unknown),
        *(("invocation", "show", str(invocation)) for invocation in invocation_ids(database)),
        ("invocation", "show", str(inspection.UNKNOWN_INVOCATION_ID)),
    ]

    for command in commands:
        here = said(capsys, *command)
        there = said(capsys, *command, "--remote", "origin")

        assert there == here, command


def test_a_production_shows_its_author_and_what_it_restores_from_a_remote(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, printed, _ = said(
        capsys, "workflow", "production", str(inspection.WORKFLOW_ID), "--remote", "origin"
    )

    assert status == 0
    assert f"Restores: {inspection.FIRST_REVISION_ID}\n" in printed
    assert "Author: Eris Discordia <eris@example.com>\n" in printed


def test_a_production_that_emits_says_the_same_here_and_on_a_remote(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with api.open(database) as instance:
        stock(instance)

    promote(str(database), COUNT_WORKFLOW_ID)
    here = said(capsys, "workflow", "production", str(COUNT_WORKFLOW_ID))
    there = said(capsys, "workflow", "production", str(COUNT_WORKFLOW_ID), "--remote", "origin")

    assert there == here
    assert "\nEmission: result <- " in here[1]


def test_a_rollback_on_a_remote_is_refused_and_reported_as_here(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZATHOTH_AUTHOR", ERIS.name)
    workflow = str(inspection.WORKFLOW_ID)

    for command in (
        ("workflow", "rollback", workflow),
        ("workflow", "rollback", str(inspection.UNKNOWN_WORKFLOW_ID)),
        ("workflow", "rollback", workflow, "--to", str(inspection.SECOND_REVISION_ID)),
    ):
        here = said(capsys, *command)
        there = said(capsys, *command, "--remote", "origin")

        assert there == here, command
        assert here[0] == 1

    SQLiteModelPortfolioRepository(database).save(
        ModelPortfolioEntry(provider="openrouter", model="first-model")
    )
    status, rolled_back, _ = said(capsys, "workflow", "rollback", workflow, "--remote", "origin")
    lines = rolled_back.splitlines()

    with api.open(database) as instance:
        (newest, *_) = instance.production.revisions(inspection.WORKFLOW_ID)

    assert status == 0
    assert lines == [
        "Workflow: deployed workflow",
        f"Workflow ID: {workflow}",
        f"Revision ID: {newest.revision_id}",
        "Status: rolled back",
        f"Restores: {inspection.FIRST_REVISION_ID}",
        f"Author: {ERIS.name}",
        f"Created At: {newest.created_at.isoformat()}",
        "",
        f"Prompt Step: {inspection.STEP_ID}",
        "Primary Model: openrouter/first-model",
    ]


def test_a_promotion_on_a_remote_is_reported_as_here(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZATHOTH_AUTHOR", ERIS.name)

    with api.open(database) as instance:
        stock(instance)

    workflow = str(COUNT_WORKFLOW_ID)
    here = said(capsys, "workflow", "promote", workflow)
    there = said(capsys, "workflow", "promote", workflow, "--remote", "origin")

    with api.open(database) as instance:
        newest, previous = instance.production.revisions(COUNT_WORKFLOW_ID)

    assert here[0] == there[0] == 0
    assert there[1] == here[1].replace(str(previous.revision_id), str(newest.revision_id)).replace(
        previous.created_at.isoformat(), newest.created_at.isoformat()
    )

    missing = str(inspection.UNKNOWN_WORKFLOW_ID)

    assert said(capsys, "workflow", "promote", missing, "--remote", "origin") == said(
        capsys, "workflow", "promote", missing
    )


def test_an_invocations_checks_from_a_remote_render_as_kept_ones_do() -> None:
    checks: tuple[Mapping[str, JsonValue], ...] = (
        {"status": "verified", "source": "doc-1", "segment": 2, "quote": "Hello", "pages": [3, 3]},
        {"status": "unverified", "source": "doc-2", "segment": None, "quote": "Bye"},
    )
    cited = (
        RecordedCitations(step_id=inspection.STEP_ID, record="a" * 64, checks=checks),
        RecordedCitations(step_id=inspection.STEP_ID, record="b" * 64, checks=None),
    )

    def link(check: Mapping[str, JsonValue]) -> str | None:
        return f"https://example.com/{check['source']}" if check["status"] == "verified" else None

    kept = create_production_invocation(
        workflow_id=inspection.WORKFLOW_ID,
        payload={"text": "cited"},
        caller_metadata={},
    )
    detail = api.InvocationDetail(
        invocation_id=kept.id,
        workflow_id=kept.workflow_id,
        created_at=kept.created_at,
        status="succeeded",
        result="OK",
        error=None,
        idempotency_key=None,
        input={"text": "cited"},
        sensitivity=api.Sensitivity.INTERNAL,
        caller_metadata={},
        run=api.InvocationRun(run_id=inspection.FIRST_RUN_ID, finished=False, resumes=2),
        command=f"azathoth invocation show {kept.id}",
        citations=tuple(
            api.CitationRecord(
                step_id=recorded.step_id,
                record=recorded.record,
                checks=None if recorded.checks is None else tuple(dict(c) for c in recorded.checks),
            )
            for recorded in cited
        ),
    )

    assert render_invocation_detail(detail, link=link) == render_production_invocation(
        kept,
        result=ProductionInvocationSuccess(invocation_id=kept.id, result="OK"),
        run_id=inspection.FIRST_RUN_ID,
        resumes=2,
        citations=cited,
        link=link,
    )


def test_the_production_commands_now_run_on_a_remote() -> None:
    assert (
        not {
            "workflow production",
            "workflow revisions",
            "workflow invocations",
            "invocation show",
            "workflow promote",
            "workflow rollback",
        }
        & NOT_YET_ON_A_REMOTE
    )


def test_an_emission_names_where_it_is_read_as_production_describes_it(
    database: Path,
) -> None:
    with api.open(database) as instance:
        stock(instance)

    promote(str(database), COUNT_WORKFLOW_ID)

    with api.open(database) as instance:
        state = instance.production.get(COUNT_WORKFLOW_ID)

    assert state is not None
    (emission,) = state.emissions
    stored = SQLiteWorkflowProductionStateRepository(database).get(COUNT_WORKFLOW_ID)

    assert stored is not None
    assert emission == api.ProductionEmission(
        name="result",
        source=describe_value_reference(stored.emissions[0].source),
    )

"""Tests that a run's citations export as Web Annotations, and link to their pages (ADR 0117)."""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth import __version__
from azathoth.citations import WEB_ANNOTATION_CONTEXT
from azathoth.cli import main
from azathoth.cli.annotations import GENERATOR
from azathoth.context import Context
from azathoth.inputs import InMemoryContentStore, file_uri
from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import stored_citation_checks
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
)
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from azathoth.workflows import (
    WorkflowProductionState,
    WorkflowRunner,
    create_production_invocation,
    journaled_citations,
)
from tests.cli.test_cited_invocation import (
    CITED_STEP_ID,
    MODEL,
    PDF,
    PROVIDER,
    REPLY,
    WORKFLOW_ID,
    cited_workflow,
)
from tests.workflows.test_citation_judging import CitingStrategy, candidate, kept_run


def run(
    *arguments: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    """Run one CLI command; return its status, output and errors."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Initialize a database, deploy the cited workflow, and give it a citing model."""

    path = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(path))
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: ModelCatalog(
            models=(ModelMetadata(provider=PROVIDER, model=MODEL, display_name=MODEL),)
        ),
    )
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: LanguageModelRegistry(
            {
                f"{PROVIDER}/{MODEL}": DeterministicLanguageModel(
                    provider=PROVIDER,
                    model=MODEL,
                    response_text=json.dumps(REPLY),
                )
            }
        ),
    )

    (tmp_path / "claim.pdf").write_bytes(PDF)

    status, _, err = run("init", capsys=capsys)

    assert status == 0, err

    open_repositories(path).production_states.set(
        WorkflowProductionState(specification=cited_workflow())
    )

    return path


def invoked(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[UUID, UUID]:
    """Invoke the workflow on the claim's PDF; return the invocation's and its run's IDs."""

    status, _, err = run(
        "workflow", "invoke", WORKFLOW_ID, "--input-file", "claim.pdf", capsys=capsys
    )

    assert status == 0, err

    repositories = open_repositories(database)
    (invocation,) = repositories.invocations.invocations()
    association = repositories.invocation_runs.get(invocation.id)

    assert association is not None

    return invocation.id, association.run_id


def test_an_invocations_verified_citations_export_as_one_collection(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation_id, run_id = invoked(database, capsys)

    status, out, err = run("invocation", "annotations", str(invocation_id), capsys=capsys)

    assert status == 0, err

    collection: dict[str, Any] = json.loads(out)

    assert collection["@context"] == WEB_ANNOTATION_CONTEXT
    assert collection["label"] == (
        f"Citations of run {run_id}: 1 verified, 1 not verified and left out."
    )
    assert collection["total"] == 1

    (annotation,) = collection["first"]["items"]
    repositories = open_repositories(database)
    ((_, digest),) = journaled_citations(repositories.run_journal, run_id)
    checks = stored_citation_checks(repositories.content, digest)

    assert checks is not None

    anchor = checks[0]["anchor"]

    assert isinstance(anchor, dict)
    assert annotation["target"] == {
        "type": "SpecificResource",
        "source": file_uri(tmp_path / "claim.pdf"),
        "selector": anchor["selectors"],
    }
    assert annotation["generator"]["name"] == GENERATOR == f"Azathoth {__version__}"
    assert annotation["body"]["value"] == f"Cited by step {CITED_STEP_ID} of run {run_id}."


def test_a_runs_citations_export_as_its_invocations_do(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation_id, run_id = invoked(database, capsys)

    _, by_invocation, _ = run("invocation", "annotations", str(invocation_id), capsys=capsys)
    status, by_run, err = run("run", "annotations", str(run_id), capsys=capsys)

    assert status == 0, err
    assert by_run == by_invocation


@pytest.mark.parametrize(
    ("command", "message"),
    [
        pytest.param("run", "Run {id} was not found.\n", id="run"),
        pytest.param("invocation", "Invocation {id} was not found.\n", id="invocation"),
    ],
)
def test_an_unknown_run_or_invocation_is_refused(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    message: str,
) -> None:
    unknown = UUID("c16f0000-0000-4000-8000-000000000001")

    assert run(command, "annotations", str(unknown), capsys=capsys) == (
        1,
        "",
        message.format(id=unknown),
    )


def test_an_invocation_with_no_run_is_refused(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation = create_production_invocation(
        workflow_id=UUID(WORKFLOW_ID),
        payload=None,
    )

    open_repositories(database).invocations.save(invocation)

    assert run("invocation", "annotations", str(invocation.id), capsys=capsys) == (
        1,
        "",
        f"Invocation {invocation.id} has no run.\n",
    )


def test_a_record_the_content_store_no_longer_holds_is_refused(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, run_id = invoked(database, capsys)
    ((_, digest),) = journaled_citations(open_repositories(database).run_journal, run_id)

    monkeypatch.setattr(
        "azathoth.cli.annotations.stored_citation_checks",
        lambda store, digest: None,
    )

    assert run("run", "annotations", str(run_id), capsys=capsys) == (
        1,
        "",
        f"Citation record {digest} of step {CITED_STEP_ID} is not in the content store.\n",
    )


def test_a_record_holding_no_checks_is_refused(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, run_id = invoked(database, capsys)
    store = open_repositories(database).content
    elsewhere = store.put(b"[]")
    real = stored_citation_checks

    monkeypatch.setattr(
        "azathoth.cli.annotations.stored_citation_checks",
        lambda store, digest: real(store, elsewhere),
    )

    assert run("run", "annotations", str(run_id), capsys=capsys) == (
        1,
        "",
        f"Content {elsewhere} is not a record of citation checks.\n",
    )


def test_a_run_with_no_cited_step_exports_an_empty_collection(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, run_id = invoked(database, capsys)

    monkeypatch.setattr("azathoth.cli.annotations.journaled_citations", lambda journal, run: ())

    status, out, err = run("run", "annotations", str(run_id), capsys=capsys)

    assert status == 0, err
    assert json.loads(out)["total"] == 0
    assert "first" not in json.loads(out)


def test_a_run_only_journaled_so_far_exports_what_its_committed_steps_checked(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    unfinished, _ = kept_run([], journal=open_repositories(database).run_journal)

    assert open_repositories(database).runs.get(unfinished.id) is None

    status, out, err = run("run", "annotations", str(unfinished.id), capsys=capsys)

    assert status == 0, err
    assert json.loads(out)["total"] == 0


def test_a_run_recorded_without_a_journal_exports_too(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorded, _ = kept_run([])
    repositories = open_repositories(database)

    repositories.runs.save(recorded)

    assert repositories.run_journal.entries(recorded.id) == ()

    status, out, err = run("run", "annotations", str(recorded.id), capsys=capsys)

    assert status == 0, err
    assert json.loads(out)["total"] == 0


def test_an_invocation_whose_run_has_not_finished_exports_its_run(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation = create_production_invocation(workflow_id=UUID(WORKFLOW_ID), payload=None)
    repositories = open_repositories(database)

    repositories.invocations.save(invocation)

    unfinished = asyncio.run(
        WorkflowRunner(journal=repositories.run_journal).run_recording_failures(
            candidate(CitingStrategy(InMemoryContentStore(), [])),
            Context(),
            invocation_id=invocation.id,
        )
    )

    assert repositories.invocation_runs.get(invocation.id) is None

    status, out, err = run("invocation", "annotations", str(invocation.id), capsys=capsys)

    assert status == 0, err
    assert json.loads(out)["label"] == f"Citations of run {unfinished.id}: 0 verified."


def test_invocation_show_links_each_verified_citation_to_its_page(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation_id, _ = invoked(database, capsys)

    status, out, err = run("invocation", "show", str(invocation_id), "--links", capsys=capsys)

    assert status == 0, err
    assert out.endswith(
        "  verified claim p1.s2 'December 14'\n"
        f"    {file_uri(tmp_path / 'claim.pdf')}#page=1\n"
        "  quote_not_found claim p2.s1 'Denied.'\n"
    )

    status, out, err = run("invocation", "show", str(invocation_id), capsys=capsys)

    assert "#page=" not in out


def test_invocation_show_refuses_links_that_expire_wrongly(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation_id, _ = invoked(database, capsys)

    monkeypatch.setenv("AZATHOTH_LINK_EXPIRY_SECONDS", "0")

    assert run("invocation", "show", str(invocation_id), "--links", capsys=capsys) == (
        1,
        "",
        "AZATHOTH_LINK_EXPIRY_SECONDS must be a whole number of seconds from 1 to 604800, "
        "not '0'.\n",
    )

    status, _, err = run("invocation", "show", str(invocation_id), capsys=capsys)

    assert status == 0, err


def test_invocation_show_links_no_check_that_did_not_verify(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation_id, run_id = invoked(database, capsys)
    repositories = open_repositories(database)
    ((_, digest),) = journaled_citations(repositories.run_journal, run_id)
    kept = stored_citation_checks(repositories.content, digest)

    assert kept is not None

    #
    # A check that did not verify is never anchored; one that somehow was is
    # still not linked.
    #
    anchored = tuple(
        {**check, "anchor": kept[0]["anchor"]} if check["status"] != "verified" else check
        for check in kept
    )

    monkeypatch.setattr(
        "azathoth.cli.production_inspection.stored_citation_checks",
        lambda store, digest: anchored,
    )

    status, out, err = run("invocation", "show", str(invocation_id), "--links", capsys=capsys)

    assert status == 0, err
    assert out.count("#page=") == 1

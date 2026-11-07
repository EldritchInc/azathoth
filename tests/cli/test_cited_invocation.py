"""Tests that documents go in and checked evidence comes out of one invocation (ADR 0116).

A PDF is segmented by the standard `segment_pdf` tool, a cited step on a
deterministic model cites the segments, every check is kept and recorded,
`invocation show` prints the checks, and each one is checked again from the
content store alone.
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.citations import SegmentedText, verify_citation
from azathoth.cli import main
from azathoth.inputs import InputOrigin, content_bytes_digest
from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import CITATIONS_RESOURCE_KIND, stored_citation_checks
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
)
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from azathoth.workflows import (
    ProductionInvocationSuccess,
    WorkflowProductionEmission,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowValueReference,
    journaled_citations,
)
from tests.standard.pdf_builder import Page, Text, pdf_document

WORKFLOW_ID = "c1650000-0000-4000-8000-000000000001"

SEGMENT_STEP_ID = "c1650000-0000-4000-8000-000000000002"

CITED_STEP_ID = "c1650000-0000-4000-8000-000000000003"

STRATEGY_ID = "c1650000-0000-4000-8000-000000000004"

PROVIDER = "test-provider"

MODEL = "citing-model"

PDF = pdf_document(
    (
        Page(texts=(Text(72, 700, "Claim 0412."), Text(72, 500, "Received on December 14."))),
        Page(texts=(Text(72, 700, "Approved."),)),
    )
)

REPLY = {
    "received": "December 14",
    "citations": [
        {"source": "claim", "segment": "p1.s2", "quote": "December 14"},
        {"source": "claim", "segment": "p2.s1", "quote": "Denied."},
    ],
}


def no_retries() -> dict[str, Any]:
    """Return a retry policy of one attempt."""

    return {
        "max_attempts": 1,
        "initial_delay_seconds": 0.0,
        "backoff_multiplier": 1.0,
        "maximum_delay_seconds": None,
    }


def cited_workflow() -> WorkflowSpecification:
    """Return a workflow that segments its PDF, then answers from it, citing segments."""

    return WorkflowSpecification.model_validate(
        {
            "metadata": {
                "id": WORKFLOW_ID,
                "name": "answer from a claim",
                "description": "Segment a claim PDF, then say when it was received, citing it.",
                "version": "1.0.0",
            },
            "steps": [
                {
                    "id": SEGMENT_STEP_ID,
                    "specification": {
                        "requirement": {
                            "name": "segment_pdf",
                            "version": "1.0.0",
                            "runtime": "process",
                        }
                    },
                    "inputs": [
                        {
                            "name": "document",
                            "source": {
                                "event_type": "workflow.input.received",
                                "field_name": "input",
                            },
                        }
                    ],
                    "outputs": [{"name": "extraction", "path": ["extraction"]}],
                    "retry_policy": no_retries(),
                },
                {
                    "id": CITED_STEP_ID,
                    "specification": {
                        "metadata": {
                            "id": STRATEGY_ID,
                            "name": "answer",
                            "description": "Say when the claim was received, citing it.",
                            "version": "1.0.0",
                        },
                        "template": {
                            "text": "{claim}\n\nWhen was the claim received?",
                            "bindings": [{"variable_name": "claim", "input_name": "claim"}],
                        },
                        "model_selection": {"provider": PROVIDER, "model": MODEL},
                        "output_format": "json",
                        "citations": {"on_unverified": "keep"},
                    },
                    "depends_on": [SEGMENT_STEP_ID],
                    "inputs": [
                        {
                            "name": "claim",
                            "source": {
                                "producer_step_id": SEGMENT_STEP_ID,
                                "name": "extraction",
                            },
                        }
                    ],
                    "outputs": [{"name": "answer"}],
                    "retry_policy": no_retries(),
                },
            ],
        }
    )


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Initialize a database, deploy the workflow, and give it a citing model; return it."""

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

    status = main(("init",))
    captured = capsys.readouterr()

    assert status == 0, captured.err

    open_repositories(path).production_states.set(
        WorkflowProductionState(
            specification=cited_workflow(),
            emissions=(
                WorkflowProductionEmission(
                    name="answer",
                    source=WorkflowValueReference(
                        producer_step_id=UUID(CITED_STEP_ID),
                        name="answer",
                    ),
                ),
            ),
        )
    )

    return path


def invoked(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> UUID:
    """Invoke the workflow on the claim's PDF; return the invocation's ID."""

    status = main(("workflow", "invoke", WORKFLOW_ID, "--input-file", "claim.pdf"))
    captured = capsys.readouterr()

    assert status == 0, captured.err

    (invocation,) = open_repositories(database).invocations.invocations()

    return invocation.id


def test_a_cited_invocation_keeps_every_check_of_what_its_model_cited(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation_id = invoked(database, capsys)
    repositories = open_repositories(database)
    result = repositories.invocations.result(invocation_id)
    association = repositories.invocation_runs.get(invocation_id)

    assert isinstance(result, ProductionInvocationSuccess)
    assert association is not None

    run = repositories.runs.get(association.run_id)

    assert run is not None

    cited = run.steps[1].execution

    assert cited is not None

    (record,) = (
        resource for resource in cited.resources if resource.kind == CITATIONS_RESOURCE_KIND
    )

    assert record.attributes == {
        "citations": 2,
        "verified": 1,
        "verified_normalized": 0,
        "quote_not_found": 1,
        "unknown_segment": 0,
    }
    assert journaled_citations(repositories.run_journal, association.run_id) == (
        (UUID(CITED_STEP_ID), record.identifier),
    )

    checks = stored_citation_checks(repositories.content, record.identifier)

    assert checks is not None
    assert cited.output == {"received": "December 14", "citations": list(checks)}
    assert result.result == {"answer": cited.output}
    assert [(check["segment"], check["status"]) for check in checks] == [
        ("p1.s2", "verified"),
        ("p2.s1", "quote_not_found"),
    ]


def test_every_kept_check_is_checked_again_from_the_content_store_alone(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation_id = invoked(database, capsys)
    repositories = open_repositories(database)
    association = repositories.invocation_runs.get(invocation_id)

    assert association is not None

    ((_, digest),) = journaled_citations(repositories.run_journal, association.run_id)
    checks = stored_citation_checks(repositories.content, digest)

    assert checks is not None

    verified = checks[0]
    anchor = verified["anchor"]

    assert isinstance(anchor, dict)
    assert anchor["digest"] == content_bytes_digest(PDF)

    extraction = anchor["extraction"]

    assert isinstance(extraction, dict)
    assert isinstance(extraction["digest"], str)

    segmented = SegmentedText.load(repositories.content, extraction["digest"])

    assert segmented is not None
    assert segmented.source_digest == anchor["digest"]

    origin = anchor.get("origin")

    for check in checks:
        assert isinstance(check["segment"], str)
        assert isinstance(check["quote"], str)

        again = verify_citation(
            segmented,
            segment_id=check["segment"],
            quote=check["quote"],
            origin=InputOrigin.model_validate(origin) if origin is not None else None,
        )

        assert again.status.value == check["status"]
        assert (
            again.anchor.model_dump(mode="json", by_alias=True)
            if again.anchor is not None
            else None
        ) == check.get("anchor")


def test_invocation_show_prints_every_check_a_cited_step_kept(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation_id = invoked(database, capsys)
    repositories = open_repositories(database)
    association = repositories.invocation_runs.get(invocation_id)

    assert association is not None

    ((_, digest),) = journaled_citations(repositories.run_journal, association.run_id)

    status = main(("invocation", "show", str(invocation_id)))
    captured = capsys.readouterr()

    assert status == 0, captured.err
    assert captured.out.endswith(
        "Citations:\n"
        f"Step {CITED_STEP_ID}: 2 citations, record {digest}\n"
        "  verified claim p1.s2 'December 14'\n"
        "  quote_not_found claim p2.s1 'Denied.'\n"
    )


def test_invocation_show_names_a_record_the_content_store_no_longer_holds(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation_id = invoked(database, capsys)
    repositories = open_repositories(database)
    association = repositories.invocation_runs.get(invocation_id)

    assert association is not None

    ((_, digest),) = journaled_citations(repositories.run_journal, association.run_id)

    monkeypatch.setattr(
        "azathoth.cli.production_inspection.stored_citation_checks",
        lambda store, digest: None,
    )

    status = main(("invocation", "show", str(invocation_id)))
    captured = capsys.readouterr()

    assert status == 0, captured.err
    assert captured.out.endswith(
        f"Citations:\nStep {CITED_STEP_ID}: record {digest} is not in the content store.\n"
    )


def test_invocation_show_refuses_a_record_that_holds_no_checks(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation_id = invoked(database, capsys)
    stored = open_repositories(database).content
    elsewhere = stored.put(b'{"checks": "none"}')
    real = stored_citation_checks

    monkeypatch.setattr(
        "azathoth.cli.production_inspection.stored_citation_checks",
        lambda store, digest: real(store, elsewhere),
    )

    status = main(("invocation", "show", str(invocation_id)))
    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err == f"Content {elsewhere} is not a record of citation checks.\n"

"""Tests that ADR 0117 quotes the real refusals and shapes of citations as evidence."""

import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.citations import (
    LINK_EXPIRY_VARIABLE,
    CitationRecord,
    LinkResolutionError,
    S3LinkResolver,
    citation_annotations,
    link_expiry_seconds,
)
from azathoth.cli.annotations import (
    AnnotationExportError,
    export_invocation_annotations,
    run_citation_records,
)
from azathoth.cli.benchmark_cases import SuppliedExpectedValue, add_benchmark_case
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    CitationExpectation,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.inputs import (
    InMemoryContentStore,
    InputProvenance,
    InputUnavailableError,
    ResolvedInput,
    content_bytes_digest,
)
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import (
    CitationEvidenceError,
    SQLiteWorkflowRunRepository,
    create_production_invocation,
    create_workflow_input_events,
    judge_citations,
    recorded_citation_checks,
)
from tests.citations.test_annotations import anchor
from tests.workflows.test_benchmark_case_source import create_run
from tests.workflows.test_citation_judging import check, kept_run, outcome, record_of, required

ROOT = Path(__file__).parents[2]

ADR = ROOT / "docs" / "adrs" / "0117-citations-as-evidence.md"

PDF = b"%PDF-1.7\n%%EOF\n"

DIGEST = content_bytes_digest(PDF)

HANDLE: JsonValue = {
    "content": {"digest": DIGEST, "media_type": "application/pdf", "size_bytes": len(PDF)}
}

PROVENANCE = InputProvenance(
    uri="file:///claims/claim-0412.pdf",
    media_type="application/pdf",
    size_bytes=len(PDF),
    digest=DIGEST,
)

CASE_ID = UUID("c1690000-0000-4000-8000-000000000001")

BENCHMARK_ID = UUID("c1690000-0000-4000-8000-000000000002")


def provenance_refusal() -> str:
    """Return the message a case naming a PDF's provenance without its handle gets."""

    with pytest.raises(ValidationError) as raised:
        BenchmarkCase.model_validate(
            {
                "id": str(CASE_ID),
                "input": {"text": "x"},
                "input_provenance": PROVENANCE.model_dump(mode="json"),
                "expected": {"description": "x", "value": 1, "comparison": "exact"},
            }
        )

    return (
        str(raised.value.errors()[0]["msg"])
        .removeprefix("Value error, ")
        .replace(str(CASE_ID), "<CASE_ID>")
    )


def store_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    """Return what add-case says of a run given a PDF the content store no longer holds."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(database))
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)

    SQLiteBenchmarkRepository(database).save(
        BenchmarkDataset(id=BENCHMARK_ID, name="claims", description="Claims.")
    )

    run = create_run(
        *create_workflow_input_events(
            ResolvedInput(value=HANDLE, media_type="application/pdf", provenance=PROVENANCE),
            producer="azathoth.test",
        )
    )

    SQLiteWorkflowRunRepository(database).save(run)

    status = add_benchmark_case(
        BENCHMARK_ID,
        run_id=run.id,
        comparison=OutcomeComparison.EXACT,
        expected=SuppliedExpectedValue(value=1),
    )

    assert status == 1

    return capsys.readouterr().err.rstrip("\n").replace(str(run.id), "<RUN_ID>")


def documented_blocks(
    language: str,
) -> list[str]:
    """Return the ADR's Decision blocks in one language."""

    text = ADR.read_text(encoding="utf-8")
    decision = text[text.index("## Decision") : text.index("## Consequences")]

    return [block.split("```", 1)[0] for block in decision.split(f"```{language}\n")[1:]]


def repeated_refusal() -> str:
    """Return the message an expectation requiring one segment twice is refused with."""

    with pytest.raises(ValidationError) as raised:
        CitationExpectation.model_validate(
            {"require": [{"source": "claim", "segment": "p1.s2"}] * 2}
        )

    return (
        str(raised.value.errors()[0]["msg"])
        .removeprefix("Value error, ")
        .replace("p1.s2", "<SEGMENT>")
        .replace("'claim'", "'<SOURCE>'")
    )


def judged_reason() -> str:
    """Return the reason of a case missing one of its two required citations."""

    return judge_citations(
        outcome(),
        required("p1.s2", "p2.s1", on_unverified="ignore"),
        [check("p1.s2"), check("p2.s1", "quote_not_found"), check("p2.s1", source="other")],
    ).reason


def unreadable(
    *,
    store: InMemoryContentStore | None,
) -> str:
    """Return why the checks of a run that kept one record cannot be read from a store."""

    run, _ = kept_run([[check("p1.s2")]])

    with pytest.raises(CitationEvidenceError) as raised:
        recorded_citation_checks(run, store)

    return str(raised.value).replace(str(run.id), "<RUN_ID>").replace(record_of(run), DIGEST)


def no_run_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    """Return what exporting an invocation whose run has not started says."""

    database = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(database))
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)

    invocation = create_production_invocation(workflow_id=CASE_ID, payload=None)

    open_repositories(database).invocations.save(invocation)

    assert export_invocation_annotations(invocation.id) == 1

    return capsys.readouterr().err.rstrip("\n").replace(str(invocation.id), "<INVOCATION_ID>")


def gone_record_refusal(
    tmp_path: Path,
    **_: object,
) -> str:
    """Return why a run's record the content store no longer holds cannot be exported."""

    stored = open_repositories(tmp_path / "azathoth.db")
    run, _store = kept_run([[check("p1.s2")]], journal=stored.run_journal)

    with pytest.raises(AnnotationExportError) as raised:
        run_citation_records(stored, run.id)

    return (
        str(raised.value)
        .replace(record_of(run), DIGEST)
        .replace(str(run.steps[0].step_id), "<STEP_ID>")
    )


def expiry_refusal() -> str:
    """Return the message an expiry that is not one is refused with."""

    with pytest.raises(LinkResolutionError) as raised:
        link_expiry_seconds({LINK_EXPIRY_VARIABLE: "<VALUE>"})

    return str(raised.value)


def boto3_refusal() -> str:
    """Return what an s3:// link without boto3 says."""

    def missing() -> object:
        raise InputUnavailableError("no boto3")

    with pytest.raises(LinkResolutionError) as raised:
        S3LinkResolver(client_factory=missing).link(anchor())

    return str(raised.value)


DOCUMENTED: list[tuple[str, Callable[..., str]]] = [
    (
        "Benchmark case <CASE_ID> names application/pdf content <DIGEST> as its input "
        "provenance, but its input is not that content's handle.",
        lambda **_: provenance_refusal(),
    ),
    (
        "Run <RUN_ID> received content <DIGEST>, which the content store no longer holds.",
        store_refusal,
    ),
    (
        "Citation expectation requires segment <SEGMENT> of source '<SOURCE>' more than once.",
        lambda **_: repeated_refusal(),
    ),
    (
        "The result matched. Citations: 1 of 2 required citations verified; 2 of 3 citations "
        "verified. Missing: segment p2.s1 of 'claim'.",
        lambda **_: judged_reason(),
    ),
    (
        "Run <RUN_ID> kept citation records, which cannot be read: it has no content store.",
        lambda **_: unreadable(store=None),
    ),
    (
        "Run <RUN_ID> kept citation record <DIGEST>, which the content store no longer holds.",
        lambda **_: unreadable(store=InMemoryContentStore()),
    ),
    (
        "Invocation <INVOCATION_ID> has no run.",
        no_run_refusal,
    ),
    (
        "Citation record <DIGEST> of step <STEP_ID> is not in the content store.",
        gone_record_refusal,
    ),
    (
        "AZATHOTH_LINK_EXPIRY_SECONDS must be a whole number of seconds from 1 to 604800, "
        "not '<VALUE>'.",
        lambda **_: expiry_refusal(),
    ),
    (
        "Links to s3:// documents need boto3, which is not installed; install azathoth-ai[worker].",
        lambda **_: boto3_refusal(),
    ),
]
"""Each refusal ADR 0117 quotes, and what produces it."""


@pytest.mark.parametrize(
    ("documented", "produce"),
    [pytest.param(*row, id=row[0][:48]) for row in DOCUMENTED],
)
def test_the_adr_quotes_the_real_refusal(
    documented: str,
    produce: Callable[..., str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert f"\n{documented}\n" in ADR.read_text(encoding="utf-8")
    assert produce(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys) == (
        documented.replace("<DIGEST>", DIGEST)
    )


def test_the_adr_quotes_no_text_the_tests_do_not_check() -> None:
    quoted = {line for block in documented_blocks("text") for line in block.splitlines()}

    assert quoted == {documented for documented, _ in DOCUMENTED}


def test_the_adr_shows_a_case_the_model_accepts() -> None:
    case, expected, _ = documented_blocks("json")
    shown = json.loads(case.replace("<SHA-256>", DIGEST).replace("482113", str(len(PDF))))

    assert BenchmarkCase.model_validate(shown).input_provenance == PROVENANCE

    outcome_shown = ExpectedOutcome.model_validate(json.loads("{" + expected + "}")["expected"])

    assert outcome_shown.citations == required("p1.s2")


def test_the_adr_is_listed_in_the_index() -> None:
    index = (ROOT / "docs" / "adrs" / "README.md").read_text(encoding="utf-8")

    assert "- [ADR 0117: Citations as Evidence](0117-citations-as-evidence.md)\n" in index


def test_the_adr_shows_the_real_shape_of_an_exported_collection() -> None:
    (_, _, shown) = documented_blocks("json")
    run_id = UUID("c1690000-0000-4000-8000-000000000003")
    step_id = UUID("c1690000-0000-4000-8000-000000000004")
    verified: dict[str, JsonValue] = {
        "source": "claim",
        "segment": "p1.s2",
        "quote": "December 14",
        "status": "verified",
        "anchor": anchor().model_dump(mode="json", by_alias=True),
    }
    exported = citation_annotations(
        run_id,
        [
            CitationRecord(
                step_id=step_id,
                record=DIGEST,
                checks=[verified, {**verified, "status": "quote_not_found"}],
            )
        ],
        generator="Azathoth <VERSION>",
    )
    text = json.dumps(exported)

    for real in (str(run_id), str(step_id)):
        text = text.replace(real, "<RUN_ID>" if real == str(run_id) else "<STEP_ID>")

    placeheld = json.loads(text)
    (annotation,) = placeheld["first"]["items"]
    annotation["target"]["selector"] = ["<SELECTORS>"]
    annotation["target"]["source"] = annotation["target"]["source"].replace(
        "s3://claims/0412.pdf?versionId=3sL4.kqtJ%2Flcp%2BXroDTDmJ",
        "s3://claims-intake/2026/11/claim-0412.pdf?versionId=<VERSION_ID>",
    )

    for identified in (placeheld, placeheld["first"], annotation):
        identified["id"] = "urn:uuid:<UUID>"

    assert placeheld == json.loads(shown)

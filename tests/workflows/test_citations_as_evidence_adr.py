"""Tests that ADR 0117 quotes the real refusals and shapes of citations as evidence."""

import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.cli.benchmark_cases import SuppliedExpectedValue, add_benchmark_case
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.inputs import InputProvenance, ResolvedInput, content_bytes_digest
from azathoth.workflows import SQLiteWorkflowRunRepository, create_workflow_input_events
from tests.workflows.test_benchmark_case_source import create_run

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
    (case,) = documented_blocks("json")
    shown = json.loads(case.replace("<SHA-256>", DIGEST).replace("482113", str(len(PDF))))

    assert BenchmarkCase.model_validate(shown).input_provenance == PROVENANCE


def test_the_adr_is_listed_in_the_index() -> None:
    index = (ROOT / "docs" / "adrs" / "README.md").read_text(encoding="utf-8")

    assert "- [ADR 0117: Citations as Evidence](0117-citations-as-evidence.md)\n" in index

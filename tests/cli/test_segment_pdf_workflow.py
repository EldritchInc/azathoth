"""Tests that a workflow segments a PDF with the standard segment_pdf tool (ADR 0114)."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.citations import (
    CitationStatus,
    SegmentedText,
    extraction_handle_from_value,
    verify_citation,
)
from azathoth.cli import main
from azathoth.inputs import PDF_MEDIA_TYPE, content_bytes_digest
from azathoth.persistence.repositories import open_repositories
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from tests.standard.pdf_builder import Page, Text, pdf_document

WORKFLOW_ID = "c4100000-0000-4000-8000-000000000001"

STEP_ID = "c4100000-0000-4000-8000-000000000002"

PDF = pdf_document(
    (
        Page(texts=(Text(72, 700, "Claim 0412."), Text(72, 500, "Received on December 14."))),
        Page(texts=(Text(72, 700, "Approved."),)),
    )
)


def segment_workflow() -> dict[str, object]:
    """Return a workflow of one step that segments the workflow's PDF."""

    return {
        "metadata": {
            "id": WORKFLOW_ID,
            "name": "segment a claim PDF",
            "description": "Divide the claim PDF the workflow is given into segments.",
            "version": "1.0.0",
        },
        "steps": [
            {
                "id": STEP_ID,
                "specification": {
                    "requirement": {
                        "name": "segment_pdf",
                        "version": "1.0.0",
                        "runtime": "process",
                    }
                },
                "depends_on": [],
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
                "conditions": [],
                "retry_policy": {
                    "max_attempts": 1,
                    "initial_delay_seconds": 0.0,
                    "backoff_multiplier": 1.0,
                    "maximum_delay_seconds": None,
                },
                "failure_policy": "fail_workflow",
            }
        ],
        "result": {"name": "extraction"},
    }


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Initialize a database with the standard tools and the workflow; return it."""

    path = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(path))
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "workflow.json").write_text(json.dumps(segment_workflow()), encoding="utf-8")
    (tmp_path / "claim.pdf").write_bytes(PDF)

    for arguments in (("init",), ("workflow", "import", "workflow.json")):
        status = main(arguments)
        captured = capsys.readouterr()

        assert status == 0, captured.err

    return path


def test_a_workflow_segments_a_pdf_and_a_citation_of_it_verifies(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(
        ("workflow", "run", WORKFLOW_ID, "--input-file", "claim.pdf", "--output", "jsonl")
    )
    captured = capsys.readouterr()

    assert status == 0, captured.err

    record = json.loads(captured.out.strip().splitlines()[-1])
    handle = extraction_handle_from_value(record["value"])

    assert handle is not None
    assert (handle.tool, handle.source_digest, handle.media_type) == (
        "segment_pdf",
        content_bytes_digest(PDF),
        PDF_MEDIA_TYPE,
    )

    repositories = open_repositories(database)
    segmented = SegmentedText.load(repositories.content, handle.digest)

    assert segmented is not None
    assert [segment.id for segment in segmented.segments] == ["p1.s1", "p1.s2", "p2.s1"]

    check = verify_citation(segmented, segment_id="p1.s2", quote="December 14")

    assert check.status is CitationStatus.VERIFIED
    assert check.anchor is not None
    assert check.anchor.extraction == handle.extraction()

    run = repositories.runs.get(UUID(record["run_id"]))

    assert run is not None
    assert run.steps[0].execution is not None

    (kept,) = (
        resource for resource in run.steps[0].execution.resources if resource.kind == "extraction"
    )

    assert kept.identifier == handle.digest
    assert kept.attributes["segments"] == 3

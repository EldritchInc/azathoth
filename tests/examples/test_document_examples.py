"""Tests that the document examples are reproducible and run as shown (ADR 0112, ADR 0114)."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

from azathoth.citations import SegmentedText
from azathoth.cli import main
from azathoth.inputs import PDF_MEDIA_TYPE
from azathoth.persistence.repositories import open_repositories
from azathoth.standard import standard_tool_documents
from azathoth.workflows import ToolStepSpecification, decode_workflow_document

PROJECT_ROOT = Path(__file__).parents[2]

EXAMPLES = PROJECT_ROOT / "examples" / "documents"

CLAIM_PDF = EXAMPLES / "claim.pdf"

WORKFLOW = EXAMPLES / "segment-claim.json"

WORKFLOW_ID = UUID("a1000000-0000-4000-8000-0000000000c0")

SEGMENTS = {
    "p1.s1": "Claim 0412",
    "p1.s2": "Filed by Ada Marsh, the insured,\non behalf of Marsh Bakery.",
    "p1.s3": "The claim was received on December 14.",
    "p2.s1": "The adjuster inspected the oven on December 19\nand found its door hinge cracked.",
    "p2.s2": "Repair is approved up to $1,200.",
}
"""Each segment of the claim, as segment_pdf divides it: one per text box."""


def claim_writer() -> ModuleType:
    """Load the script that writes the claim's PDF, without running it."""

    spec = importlib.util.spec_from_file_location("make_claim_pdf", EXAMPLES / "make_claim_pdf.py")

    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def test_the_claim_is_the_pdf_its_script_writes() -> None:
    assert CLAIM_PDF.read_bytes() == claim_writer().claim_pdf()
    assert CLAIM_PDF.read_bytes().startswith(b"%PDF-1.7\n")


def test_git_never_rewrites_a_pdfs_line_endings() -> None:
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()

    assert "*.pdf binary" in attributes
    assert b"\x00" not in CLAIM_PDF.read_bytes()
    assert b"\n" in CLAIM_PDF.read_bytes()


def test_the_workflow_divides_its_input_with_the_standard_segment_pdf() -> None:
    workflow = decode_workflow_document(WORKFLOW.read_text(encoding="utf-8"))
    (step,) = workflow.steps
    (segment_pdf,) = (
        document
        for document in standard_tool_documents()
        if document.definition.name == "segment_pdf"
    )

    assert workflow.metadata.id == WORKFLOW_ID
    assert isinstance(step.specification, ToolStepSpecification)
    assert step.specification.requirement.name == "segment_pdf"
    assert step.specification.requirement.version == segment_pdf.definition.version
    assert workflow.result is not None
    assert workflow.result.name == "extraction"


def test_the_workflow_segments_the_claim_as_shown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    monkeypatch.setenv("AZATHOTH_DATABASE", str(database))

    assert main(["init"]) == 0
    assert main(["workflow", "import", str(WORKFLOW)]) == 0

    capsys.readouterr()

    assert (
        main(
            [
                "workflow",
                "run",
                str(WORKFLOW_ID),
                "--input-file",
                str(CLAIM_PDF),
                "--output",
                "result",
            ]
        )
        == 0
    )

    handle = json.loads(capsys.readouterr().out)["extraction"]
    digest = hashlib.sha256(CLAIM_PDF.read_bytes()).hexdigest()

    assert (handle["tool"], handle["source_digest"], handle["media_type"]) == (
        "segment_pdf",
        digest,
        PDF_MEDIA_TYPE,
    )

    kept = open_repositories(database).content.get(handle["digest"])

    assert kept is not None

    extraction = SegmentedText.model_validate_json(kept)

    assert {
        segment.id: extraction.text[segment.start : segment.end] for segment in extraction.segments
    } == SEGMENTS
    assert [page.page for page in extraction.pages] == [1, 2]

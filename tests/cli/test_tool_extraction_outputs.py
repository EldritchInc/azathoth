"""Tests that a document tool's extraction is kept, recorded and citable (ADR 0114)."""

import json
import sys
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
from azathoth.inputs import content_bytes_digest
from azathoth.persistence.repositories import open_repositories
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE

TOOL_ID = "c1600000-0000-4000-8000-000000000001"

WORKFLOW_ID = "c1600000-0000-4000-8000-000000000003"

STEP_ID = "c1600000-0000-4000-8000-000000000004"

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

SEGMENT_SOURCE = (
    "import json\nimport sys\n\n"
    "document = json.load(sys.stdin)['document']\n"
    "text = 'Claim 0412.\\n\\nReceived on December 14.'\n"
    "json.dump(\n"
    "    {\n"
    "        'extraction': {\n"
    "            'tool': 'segment_claims',\n"
    "            'version': '1',\n"
    "            'source_digest': document['digest'],\n"
    "            'media_type': document['media_type'],\n"
    "            'text': text,\n"
    "            'segments': [\n"
    "                {'id': 'p1.s1', 'start': 0, 'end': 11, 'page': 1},\n"
    "                {'id': 'p1.s2', 'start': 13, 'end': len(text), 'page': 1},\n"
    "            ],\n"
    "        }\n"
    "    },\n"
    "    sys.stdout,\n"
    ")\n"
)
"""A document tool that extracts the same two segments from any document."""


def segment_tool() -> dict[str, object]:
    """Return a process tool with one content input and an extraction output."""

    return {
        "definition": {
            "id": TOOL_ID,
            "name": "segment_claims",
            "description": "Divide a claim into segments.",
            "version": "1.0.0",
            "input_schema": {"json_schema": {"type": "object"}},
            "output_schema": {"json_schema": {"type": "object"}},
        },
        "implementations": [
            {
                "id": "c1600000-0000-4000-8000-000000000002",
                "tool_id": TOOL_ID,
                "tool_version": "1.0.0",
                "version": "1.0.0",
                "runtime": "process",
                "entrypoint": "run",
                "source": SEGMENT_SOURCE,
                "command": [sys.executable],
                "timeout_seconds": 60.0,
                "content_inputs": ["document"],
                "extraction_output": "extraction",
            }
        ],
        "test_cases": [],
    }


def segment_workflow() -> dict[str, object]:
    """Return a workflow of one step that segments the workflow's document."""

    return {
        "metadata": {
            "id": WORKFLOW_ID,
            "name": "segment a claim",
            "description": "Divide the claim the workflow is given into segments.",
            "version": "1.0.0",
        },
        "steps": [
            {
                "id": STEP_ID,
                "specification": {
                    "requirement": {
                        "name": "segment_claims",
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
    """Import the segmenting tool and workflow; return the database."""

    path = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(path))
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "tool.json").write_text(json.dumps(segment_tool()), encoding="utf-8")
    (tmp_path / "workflow.json").write_text(json.dumps(segment_workflow()), encoding="utf-8")
    (tmp_path / "claim.pdf").write_bytes(PDF)

    for arguments in (("tool", "import", "tool.json"), ("workflow", "import", "workflow.json")):
        status = main(arguments)
        captured = capsys.readouterr()

        assert status == 0, captured.err

    return path


def test_a_document_tools_extraction_is_kept_and_cited(
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
    assert (handle.tool, handle.source_digest) == ("segment_claims", content_bytes_digest(PDF))

    repositories = open_repositories(database)
    segmented = SegmentedText.load(repositories.content, handle.digest)

    assert segmented is not None
    assert segmented.handle() == handle

    check = verify_citation(segmented, segment_id="p1.s2", quote="December 14")

    assert check.status is CitationStatus.VERIFIED
    assert check.anchor is not None
    assert check.anchor.extraction == handle.extraction()

    run = repositories.runs.get(UUID(record["run_id"]))

    assert run is not None
    assert run.steps[0].execution is not None
    assert [(resource.kind, resource.identifier) for resource in run.steps[0].execution.resources][
        1
    ] == ("extraction", handle.digest)

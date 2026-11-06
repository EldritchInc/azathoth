"""Tests that every entry point gives a tool step the documents its run received (ADR 0114)."""

import base64
import hashlib
import json
import sys
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import main
from azathoth.context import LineageRun, LineageStep, StepLineage, encode_step_lineage
from azathoth.inputs import content_bytes_digest
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE

TOOL_ID = "c1200000-0000-4000-8000-000000000001"

WORKFLOW_ID = "c1200000-0000-4000-8000-000000000003"

STEP_ID = "c1200000-0000-4000-8000-000000000004"

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

DIGEST = content_bytes_digest(PDF)

HANDLE = json.dumps(
    {"content": {"digest": DIGEST, "media_type": "application/pdf", "size_bytes": len(PDF)}}
)

HASH_SOURCE = (
    "import hashlib\nimport json\nimport sys\n\n"
    "document = json.load(sys.stdin)['document']\n\n"
    "with open(document['path'], 'rb') as file:\n"
    "    json.dump({'sha256': hashlib.sha256(file.read()).hexdigest()}, sys.stdout)\n"
)
"""A tool that reports the SHA-256 of the file it was given."""


def hash_tool() -> dict[str, object]:
    """Return a process tool taking one content input."""

    return {
        "definition": {
            "id": TOOL_ID,
            "name": "hash_document",
            "description": "Report the SHA-256 of a document.",
            "version": "1.0.0",
            "input_schema": {"json_schema": {"type": "object"}},
            "output_schema": {
                "json_schema": {
                    "type": "object",
                    "properties": {"sha256": {"type": "string"}},
                    "required": ["sha256"],
                }
            },
        },
        "implementations": [
            {
                "id": "c1200000-0000-4000-8000-000000000002",
                "tool_id": TOOL_ID,
                "tool_version": "1.0.0",
                "version": "1.0.0",
                "runtime": "process",
                "entrypoint": "run",
                "source": HASH_SOURCE,
                "command": [sys.executable],
                "timeout_seconds": 60.0,
                "content_inputs": ["document"],
            }
        ],
        "test_cases": [],
    }


def hash_workflow() -> dict[str, object]:
    """Return a workflow of one step that hashes the workflow's document."""

    return {
        "metadata": {
            "id": WORKFLOW_ID,
            "name": "hash a document",
            "description": "Hash the document the workflow is given.",
            "version": "1.0.0",
        },
        "steps": [
            {
                "id": STEP_ID,
                "specification": {
                    "requirement": {
                        "name": "hash_document",
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
                "outputs": [{"name": "sha256", "path": ["sha256"]}],
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
        "result": {"name": "sha256"},
    }


def cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one command, returning its status, stdout and stderr."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


@pytest.fixture
def workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Import and promote the hashing tool and workflow; return the working folder."""

    monkeypatch.setenv("AZATHOTH_DATABASE", str(tmp_path / "azathoth.db"))
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "tool.json").write_text(json.dumps(hash_tool()), encoding="utf-8")
    (tmp_path / "workflow.json").write_text(json.dumps(hash_workflow()), encoding="utf-8")
    (tmp_path / "claim.pdf").write_bytes(PDF)

    for arguments in (
        ("tool", "import", "tool.json"),
        ("workflow", "import", "workflow.json"),
        ("workflow", "promote", WORKFLOW_ID),
    ):
        status, _, errors = cli(capsys, *arguments)

        assert status == 0, errors

    return tmp_path


def final_record(
    output: str,
) -> dict[str, object]:
    """Return the last JSON Lines record a command printed."""

    record = json.loads(output.strip().splitlines()[-1])

    assert isinstance(record, dict)

    return record


SHA256 = hashlib.sha256(PDF).hexdigest()

RESULTS = {
    "run": SHA256,
    "invoke": {"result": SHA256},
}
"""What each command reports as its value: a production invocation names its result."""


@pytest.mark.parametrize("command", sorted(RESULTS))
def test_a_workflow_given_a_pdf_file_gives_its_tool_the_pdf(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    status, output, errors = cli(
        capsys,
        "workflow",
        command,
        WORKFLOW_ID,
        "--input-file",
        "claim.pdf",
        "--output",
        "jsonl",
    )

    assert status == 0, errors
    assert final_record(output)["value"] == RESULTS[command]


def test_a_job_given_an_inline_pdf_gives_its_tool_the_pdf(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (workspace / "request.json").write_text(
        json.dumps(
            {
                "kind": "invoke",
                "version": 1,
                "idempotency_key": "claim-0412",
                "workflow_id": WORKFLOW_ID,
                "input": {
                    "value": base64.b64encode(PDF).decode("ascii"),
                    "media_type": "application/pdf",
                },
            }
        ),
        encoding="utf-8",
    )

    status, output, errors = cli(capsys, "job", "run", "request.json")

    assert status == 0, errors

    result = json.loads(output)

    assert result["status"] == "succeeded", result
    assert result["result"] == RESULTS["invoke"]


def test_a_handle_the_run_never_received_reaches_no_tool(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    #
    # The PDF is in the store, from an earlier run, and the handle names it
    # exactly; this run was given only the handle, as plain JSON.
    #
    status, _, errors = cli(capsys, "workflow", "run", WORKFLOW_ID, "--input-file", "claim.pdf")

    assert status == 0, errors

    status, output, errors = cli(capsys, "workflow", "run", WORKFLOW_ID, "--input", HANDLE)

    assert status != 0
    assert (
        f"Content input 'document' of tool hash_document names content {DIGEST}, "
        "which this run never received."
    ) in output + errors


def test_a_child_is_given_the_documents_its_parent_received(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, output, errors = cli(
        capsys,
        "workflow",
        "run",
        WORKFLOW_ID,
        "--input-file",
        "claim.pdf",
        "--output",
        "jsonl",
    )

    assert status == 0, errors

    parent = UUID(str(final_record(output)["run_id"]))

    monkeypatch.setenv(
        LINEAGE_ENVIRONMENT_VARIABLE,
        encode_step_lineage(
            StepLineage(
                step=LineageStep(
                    workflow_id=UUID(WORKFLOW_ID),
                    run_id=parent,
                    step_id=UUID(STEP_ID),
                    attempt=1,
                ),
                depth=0,
                root=LineageRun(workflow_id=UUID(WORKFLOW_ID), run_id=parent),
            )
        ),
    )

    status, output, errors = cli(
        capsys, "workflow", "invoke", WORKFLOW_ID, "--input", HANDLE, "--output", "jsonl"
    )

    assert status == 0, errors
    assert final_record(output)["value"] == RESULTS["invoke"]

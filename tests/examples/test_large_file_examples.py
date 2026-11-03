"""Tests proving the large-file example: split, map, read, count, sum (ADR 0110).

The example runs end to end here, through Azathoth's own process runtime,
against a stand-in for S3 over HTTP: the S3 tools reach it with real boto3,
through the `AWS_*` variables each process is granted, as they reach S3 on a
worker. Real S3 meets the example only in the sandbox deployment.
"""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from azathoth.cli import main
from azathoth.jobs import decode_job_request
from azathoth.tools import (
    LINEAGE_ENVIRONMENT_VARIABLE,
    ProcessToolExecutor,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowConstantValue,
    decode_workflow_document,
    encode_workflow_document,
)
from tests.examples.s3_server import S3Objects, s3_server
from tests.examples.test_word_count_benchmark_examples import configure_walkthrough, run_cli

PROJECT_ROOT = Path(__file__).parents[2]

EXAMPLE = PROJECT_ROOT / "examples" / "large-file"

CHILD_DOCUMENT = EXAMPLE / "workflows" / "count-words-in-chunk.json"

PARENT_DOCUMENT = EXAMPLE / "workflows" / "count-words-in-large-file.json"

SUM_DOCUMENT = EXAMPLE / "tools" / "sum-results.json"

REQUEST = EXAMPLE / "request.json"

AWS_GUIDE = PROJECT_ROOT / "docs" / "aws.md"

PROCESS_TOOL_DOCUMENT = PROJECT_ROOT / "examples" / "tools" / "word-count-process.json"

CHILD_WORKFLOW_ID = UUID("a1000000-0000-4000-8000-000000000008")

PARENT_WORKFLOW_ID = UUID("a1000000-0000-4000-8000-000000000009")

BUCKET = "azathoth-data"

SOURCE_KEY = "work/inbox/book.txt"

CHUNKS = "work/chunks/"

MEBIBYTE = 1024 * 1024


def book() -> bytes:
    """Return a text of whole lines, a little over two and a half chunks long."""

    line = "The old ones wait in sunken cities, and they dream.\n"
    count = (MEBIBYTE * 5 // 2) // len(line) + 1

    return "".join(f"{index} {line}" for index in range(count)).encode("utf-8")


def tool_steps(
    path: Path,
) -> list[ToolStepSpecification]:
    """Return the tool specifications of one workflow's steps, in order."""

    workflow = decode_workflow_document(path.read_text(encoding="utf-8"))
    specifications = []

    for step in workflow.steps:
        assert isinstance(step.specification, ToolStepSpecification)
        specifications.append(step.specification)

    return specifications


def constant(
    path: Path,
    tool: str,
    name: str,
) -> Any:
    """Return the constant one workflow binds to one input of one tool's step."""

    workflow = decode_workflow_document(path.read_text(encoding="utf-8"))

    for step in workflow.steps:
        assert isinstance(step.specification, ToolStepSpecification)

        if step.specification.requirement.name == tool:
            (binding,) = (binding for binding in step.inputs if binding.name == name)
            assert isinstance(binding.source, WorkflowConstantValue)

            return binding.source.value

    raise AssertionError(f"no {tool} step")


@pytest.fixture
def s3() -> Iterator[tuple[str, S3Objects]]:
    """Serve a stand-in for S3 for one test."""

    pytest.importorskip("boto3")

    with s3_server() as served:
        yield served


@pytest.fixture
def deployed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    s3: tuple[str, S3Objects],
) -> S3Objects:
    """Deploy the example as the AWS guide does, over the stand-in; return its objects."""

    endpoint, objects = s3
    configure_walkthrough(monkeypatch, tmp_path)

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3", endpoint)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-aws-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-aws-credentials"))

    run_cli(capsys, "tool", "install-standard")

    for path in (PROCESS_TOOL_DOCUMENT, SUM_DOCUMENT):
        run_cli(capsys, "tool", "import", str(path))

    for path in (CHILD_DOCUMENT, PARENT_DOCUMENT):
        run_cli(capsys, "workflow", "import", str(path))

    for workflow_id in (CHILD_WORKFLOW_ID, PARENT_WORKFLOW_ID):
        run_cli(capsys, "workflow", "promote", str(workflow_id))

    return objects


# The documents


@pytest.mark.parametrize("path", [CHILD_DOCUMENT, PARENT_DOCUMENT], ids=lambda path: path.name)
def test_the_example_workflows_are_canonical(
    path: Path,
) -> None:
    encoded = path.read_text(encoding="utf-8")

    assert encode_workflow_document(decode_workflow_document(encoded)) == encoded.rstrip("\n")


def test_the_example_tool_is_canonical() -> None:
    encoded = SUM_DOCUMENT.read_text(encoding="utf-8")

    assert encode_tool_document(decode_tool_document(encoded)) == encoded.rstrip("\n")


def test_the_parent_splits_maps_the_child_over_every_chunk_and_sums() -> None:
    steps = [
        (step.requirement.name, step.requirement.version) for step in tool_steps(PARENT_DOCUMENT)
    ]
    split = constant(PARENT_DOCUMENT, "split_s3_object", "settings")
    mapped = constant(PARENT_DOCUMENT, "map_workflow", "settings")

    assert steps == [
        ("split_s3_object", "1.0.0"),
        ("map_workflow", "1.0.0"),
        ("sum_results", "1.0.0"),
    ]
    assert mapped["workflow_id"] == str(CHILD_WORKFLOW_ID)
    assert mapped["max_items"] == split["max_chunks"]
    assert split["destination_prefix"] == f"s3://{BUCKET}/{CHUNKS}"


def test_the_child_selects_its_chunk_reads_it_and_counts_it() -> None:
    steps = [
        (step.requirement.name, step.requirement.version) for step in tool_steps(CHILD_DOCUMENT)
    ]
    split = constant(PARENT_DOCUMENT, "split_s3_object", "settings")
    read = constant(CHILD_DOCUMENT, "read_s3_object", "settings")

    assert steps == [
        ("json_select", "1.0.0"),
        ("read_s3_object", "1.0.0"),
        ("word_count_process", "1.0.0"),
    ]
    assert constant(CHILD_DOCUMENT, "json_select", "path") == ["item", "uri"]
    assert read == {"media_type": "text/plain", "max_bytes": split["chunk_bytes"]}


def test_the_request_is_a_job_for_the_parent_over_a_source_beside_its_chunks() -> None:
    request = decode_job_request(json.loads(REQUEST.read_text(encoding="utf-8")))

    assert request.workflow_id == PARENT_WORKFLOW_ID
    assert request.model_dump(mode="json")["input"]["value"] == f"s3://{BUCKET}/{SOURCE_KEY}"


def test_sum_results_adds_every_childs_result() -> None:
    (implementation,) = decode_tool_document(
        SUM_DOCUMENT.read_text(encoding="utf-8")
    ).implementations

    output = asyncio.run(
        ProcessToolExecutor().execute(
            implementation,
            {"results": [{"result": 4}, {"result": 2}, {"result": 3}]},
        )
    )

    assert output == {"total": 9}


# The example, end to end


def test_the_example_counts_every_word_of_a_file_larger_than_a_chunk(
    deployed: S3Objects,
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = book()
    deployed.put(BUCKET, SOURCE_KEY, content)

    status = main(("job", "run", str(REQUEST)))
    captured = capsys.readouterr()
    (line,) = captured.out.splitlines()
    result = json.loads(line)

    assert (status, captured.err) == (0, "")
    assert result["status"] == "succeeded"
    assert result["result"] == {"result": len(content.split())}

    #
    # The AWS guide shows this very line.
    #
    documented = line.replace(result["invocation_id"], "<INVOCATION_ID>").replace(
        f'{{"result": {len(content.split())}}}', '{"result": <WORDS>}'
    )

    assert f"```json\n{documented}\n```" in AWS_GUIDE.read_text(encoding="utf-8")

    #
    # Three chunks of whole lines, each at most a mebibyte, in one attempt's
    # folder, that put the source back together.
    #
    keys = deployed.keys(BUCKET, CHUNKS)
    chunks = [deployed.get(BUCKET, key) for key in keys]

    assert [key.rsplit("/", 1)[1] for key in keys] == [
        "chunk-000000",
        "chunk-000001",
        "chunk-000002",
    ]
    assert len({key.rsplit("/", 1)[0] for key in keys}) == 1
    assert keys[0].endswith("/1/chunk-000000")
    assert all(len(chunk) <= MEBIBYTE and chunk.endswith(b"\n") for chunk in chunks)
    assert b"".join(chunks) == content

    #
    # The source was read twice and each chunk once.
    #
    reads = [path for method, path in deployed.calls if method == "GET"]

    assert reads.count(f"{BUCKET}/{SOURCE_KEY}") == 2
    assert sorted(path for path in reads if path != f"{BUCKET}/{SOURCE_KEY}") == [
        f"{BUCKET}/{key}" for key in keys
    ]


def test_a_missing_source_fails_the_run_with_the_tools_message(
    deployed: S3Objects,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(
        (
            "workflow",
            "run",
            str(PARENT_WORKFLOW_ID),
            "--input",
            json.dumps(f"s3://{BUCKET}/work/inbox/missing.txt"),
            "--output",
            "result",
        )
    )
    captured = capsys.readouterr()

    assert status != 0
    assert (
        f"split_s3_object could not read s3://{BUCKET}/work/inbox/missing.txt: 404: Not Found."
        in captured.err
    )
    assert deployed.keys(BUCKET, CHUNKS) == []

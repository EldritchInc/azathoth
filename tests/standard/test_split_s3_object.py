"""Tests for `split_s3_object`: one S3 object streamed into chunk objects (ADR 0110).

The tool's script keeps its work in functions that take an S3 client, so
these tests load its source and call them with a real client answered by
botocore's `Stubber`; nothing reaches AWS. Its refusals of bad inputs run
through the real process runtime. boto3 ships no types, so it is imported
by name, and the tests that need it are skipped where it is not installed.
"""

import importlib
import io
import json
import os
import random
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import LineageRun, LineageStep, StepLineage, encode_step_lineage
from tests.standard.harness import (
    standard_document,
    standard_implementation,
    standard_tool_failure,
)

PROJECT_ROOT = Path(__file__).parents[2]

STANDARD_README = PROJECT_ROOT / "src" / "azathoth" / "standard" / "README.md"

SOURCE_BUCKET = "tenix-work"

SOURCE_KEY = "inbox/large.txt"

SOURCE_URI = f"s3://{SOURCE_BUCKET}/{SOURCE_KEY}"

DESTINATION_BUCKET = "tenix-chunks"

RUN_ID = UUID("e8000000-0000-4000-8000-000000000001")

STEP_ID = UUID("e8000000-0000-4000-8000-000000000002")

FOLDER = f"chunks/{RUN_ID}/{STEP_ID}/1/"

ETAG = '"9b2cf535f27731c974343645a3985328"'

VERSION_ID = "3HL4kqtJlcpXroDTDmJ.rmSpXd3dIbrH"

#
# Every message the README documents for the tool, with its placeholders.
#
DOCUMENTED = (
    "split_s3_object needs 'settings' to be an object.",
    "split_s3_object needs 'uri' to be an s3:// URI naming an object.",
    "split_s3_object needs 'destination_prefix' to be an s3:// URI naming a bucket.",
    "split_s3_object needs 'mode' to be 'lines' or 'bytes'.",
    "split_s3_object needs 'chunk_bytes' to be a whole number from 1 to 104857600.",
    "split_s3_object needs 'max_chunks' to be a whole number of at least 1.",
    "split_s3_object writes chunks only from a workflow step, and was not run in one.",
    "split_s3_object needs boto3, which is not installed; install azathoth-ai[worker].",
    "split_s3_object could not read <URI>: <CODE>: <MESSAGE>.",
    "split_s3_object could not read <URI>: <REASON>.",
    "split_s3_object could not write <URI>: <CODE>: <MESSAGE>.",
    "split_s3_object would split <URI> into <COUNT> chunks, more than its max_chunks of "
    "<MAX_CHUNKS>.",
    "split_s3_object would split <URI> into more than its max_chunks of <MAX_CHUNKS> chunks.",
    "split_s3_object found a line at byte <BYTE> of <URI> longer than its chunk_bytes of "
    "<CHUNK_BYTES>.",
    "split_s3_object found <URI> changed while splitting it.",
)


def lineage(
    *,
    attempt: int = 1,
) -> str:
    """Return the lineage a step attempt gives the tool, as the engine encodes it."""

    run = LineageRun(workflow_id=UUID("e8000000-0000-4000-8000-000000000010"), run_id=RUN_ID)

    return encode_step_lineage(
        StepLineage(
            step=LineageStep(
                workflow_id=run.workflow_id,
                run_id=RUN_ID,
                step_id=STEP_ID,
                attempt=attempt,
            ),
            depth=0,
            root=run,
        )
    )


def script() -> dict[str, Any]:
    """Load the tool's source as a module that does not run, and return its names."""

    namespace: dict[str, Any] = {"__name__": "split_s3_object"}
    source = standard_implementation("split_s3_object").source

    exec(compile(source, "split_s3_object", "exec"), namespace)

    return namespace


TOOL = script()
"""The tool's functions and constants, loaded once."""

FAILURE: type[Exception] = TOOL["Failure"]
"""What the tool raises for every failure it reports."""


def inputs(
    **settings: JsonValue,
) -> dict[str, JsonValue]:
    """Return the tool's inputs for the source, with some settings."""

    return {
        "settings": {
            "destination_prefix": f"s3://{DESTINATION_BUCKET}/chunks/",
            "max_chunks": 100,
            **settings,
        },
        "uri": SOURCE_URI,
    }


def plan(
    **settings: JsonValue,
) -> dict[str, Any]:
    """Return the tool's plan of a split of the source, from one step attempt."""

    result: dict[str, Any] = TOOL["parse"](inputs(**settings), lineage())

    return result


def failure(
    error: pytest.ExceptionInfo[BaseException],
) -> tuple[int, str]:
    """Return the status and message of one of the tool's failures."""

    value: Any = error.value

    return value.status, value.message


def assert_documented(
    message: str,
    replacements: dict[str, str],
) -> None:
    """Check one real message is a documented one, once its values are placeholders."""

    for value, placeholder in replacements.items():
        message = message.replace(value, placeholder)

    assert message in DOCUMENTED, message


@pytest.fixture
def client() -> Any:
    """Return a real S3 client with fixed credentials, for the Stubber."""

    pytest.importorskip("boto3")

    return (
        importlib.import_module("boto3")
        .session.Session()
        .client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
    )


@pytest.fixture
def stubber(
    client: Any,
) -> Iterator[Any]:
    """Stub every call the client makes, and require each stubbed call."""

    stubber_type = importlib.import_module("botocore.stub").Stubber

    with stubber_type(client) as active:
        yield active
        active.assert_no_pending_responses()


def body(
    content: bytes,
) -> Any:
    """Return an object body as boto3 returns it."""

    streaming = importlib.import_module("botocore.response").StreamingBody

    return streaming(io.BytesIO(content), len(content))


def expect_head(
    stubber: Any,
    size: int,
    *,
    version_id: str | None = None,
    content_type: str = "text/plain",
) -> None:
    """Expect the source's HEAD, answered with its size, ETag and version."""

    response: dict[str, Any] = {"ContentLength": size, "ETag": ETAG, "ContentType": content_type}

    if version_id is not None:
        response["VersionId"] = version_id

    stubber.add_response("head_object", response, {"Bucket": SOURCE_BUCKET, "Key": SOURCE_KEY})


def expect_get(
    stubber: Any,
    content: bytes,
    *,
    version_id: str | None = None,
) -> None:
    """Expect one read of the source, pinned to the version its HEAD saw."""

    pin = {"VersionId": version_id} if version_id is not None else {"IfMatch": ETAG}

    stubber.add_response(
        "get_object",
        {"Body": body(content), "ContentLength": len(content)},
        {"Bucket": SOURCE_BUCKET, "Key": SOURCE_KEY, **pin},
    )


def expect_put(
    stubber: Any,
    index: int,
    content: bytes,
    *,
    content_type: str = "text/plain",
) -> None:
    """Expect one chunk written under the attempt's folder."""

    stubber.add_response(
        "put_object",
        {"ETag": '"chunk"'},
        {
            "Bucket": DESTINATION_BUCKET,
            "Key": f"{FOLDER}chunk-{index:06d}",
            "Body": content,
            "ContentType": content_type,
        },
    )


def chunk(
    index: int,
    size: int,
) -> dict[str, JsonValue]:
    """Return one chunk's entry in the tool's output."""

    return {
        "uri": f"s3://{DESTINATION_BUCKET}/{FOLDER}chunk-{index:06d}",
        "index": index,
        "size_bytes": size,
    }


def source(
    size: int,
    *,
    version_id: str | None = None,
) -> dict[str, JsonValue]:
    """Return the source's entry in the tool's output."""

    return {
        "uri": SOURCE_URI,
        "etag": ETAG.strip('"'),
        "version_id": version_id,
        "size_bytes": size,
    }


# Splitting at lines

TEXT = b"alpha\nbeta\ngamma delta\n\nomega"

#
# With 12-byte chunks: two lines that fit together, then a line of exactly
# 12 bytes, then an empty line and a last line without a newline.
#
TEXT_CHUNKS = (b"alpha\nbeta\n", b"gamma delta\n", b"\nomega")


@pytest.mark.parametrize("read_bytes", [1, 4, 11, 12, 13, 1024])
def test_lines_mode_ends_each_chunk_after_a_newline_and_within_chunk_bytes(
    client: Any,
    stubber: Any,
    read_bytes: int,
) -> None:
    expect_head(stubber, len(TEXT))
    expect_get(stubber, TEXT)
    expect_get(stubber, TEXT)

    for index, content in enumerate(TEXT_CHUNKS):
        expect_put(stubber, index, content)

    output = TOOL["split"](client, plan(chunk_bytes=12), read_bytes=read_bytes)

    assert output == {
        "chunks": [chunk(index, len(content)) for index, content in enumerate(TEXT_CHUNKS)],
        "count": 3,
        "source": source(len(TEXT)),
    }
    assert b"".join(TEXT_CHUNKS) == TEXT


def packed_lines(
    content: bytes,
    chunk_bytes: int,
) -> list[bytes]:
    """Pack whole lines greedily into chunks of at most chunk_bytes: the reference split."""

    chunks: list[bytes] = []
    current = b""

    for line in content.splitlines(keepends=True):
        if len(current) + len(line) > chunk_bytes:
            chunks.append(current)
            current = b""

        current += line

    return [*chunks, current] if current else chunks


@pytest.mark.parametrize("seed", range(25))
def test_lines_mode_packs_whole_lines_as_the_reference_does(
    client: Any,
    stubber: Any,
    seed: int,
) -> None:
    generator = random.Random(seed)
    chunk_bytes = generator.randint(1, 40)
    lines = [
        b"x" * generator.randint(0, chunk_bytes - 1) + b"\n"
        for _ in range(generator.randint(0, 30))
    ]
    content = b"".join(lines) + b"y" * generator.randint(0, chunk_bytes)
    expected = packed_lines(content, chunk_bytes)

    expect_head(stubber, len(content))

    if content:
        expect_get(stubber, content)
        expect_get(stubber, content)

    for index, part in enumerate(expected):
        expect_put(stubber, index, part)

    output = TOOL["split"](
        client,
        plan(chunk_bytes=chunk_bytes, max_chunks=1000),
        read_bytes=generator.randint(1, 64),
    )

    assert [entry["size_bytes"] for entry in output["chunks"]] == [len(part) for part in expected]


def test_lines_mode_is_the_default() -> None:
    assert plan()["mode"] == "lines"


@pytest.mark.parametrize("read_bytes", [1, 4, 1024])
def test_a_line_longer_than_chunk_bytes_is_refused_before_anything_is_written(
    client: Any,
    stubber: Any,
    read_bytes: int,
) -> None:
    content = b"short\n" + b"x" * 13 + b"\nend\n"
    expect_head(stubber, len(content))
    expect_get(stubber, content)

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan(chunk_bytes=12), read_bytes=read_bytes)

    assert failure(raised) == (
        1,
        f"split_s3_object found a line at byte 6 of {SOURCE_URI} longer than its "
        "chunk_bytes of 12.",
    )
    assert_documented(
        failure(raised)[1],
        {SOURCE_URI: "<URI>", "byte 6": "byte <BYTE>", "of 12": "of <CHUNK_BYTES>"},
    )


def test_a_source_too_large_for_max_chunks_of_lines_is_refused_without_reading_it(
    client: Any,
    stubber: Any,
) -> None:
    expect_head(stubber, 20)

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan(chunk_bytes=4, max_chunks=4))

    assert failure(raised) == (
        1,
        f"split_s3_object would split {SOURCE_URI} into more than its max_chunks of 4 chunks.",
    )
    assert_documented(failure(raised)[1], {SOURCE_URI: "<URI>", "of 4 ": "of <MAX_CHUNKS> "})


def test_lines_needing_more_than_max_chunks_are_refused_before_anything_is_written(
    client: Any,
    stubber: Any,
) -> None:
    #
    # 14 bytes in 5-byte chunks could fit in three, but its lines need four.
    #
    content = b"aaa\nbbb\nccc\nd\n"
    expect_head(stubber, len(content))
    expect_get(stubber, content)

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan(chunk_bytes=5, max_chunks=3))

    assert failure(raised) == (
        1,
        f"split_s3_object would split {SOURCE_URI} into more than its max_chunks of 3 chunks.",
    )


def test_lines_needing_exactly_max_chunks_are_split(
    client: Any,
    stubber: Any,
) -> None:
    content = b"aaa\nbbb\nccc\nd\n"
    expect_head(stubber, len(content))
    expect_get(stubber, content)
    expect_get(stubber, content)

    for index, part in enumerate((b"aaa\n", b"bbb\n", b"ccc\n", b"d\n")):
        expect_put(stubber, index, part)

    output = TOOL["split"](client, plan(chunk_bytes=5, max_chunks=4))

    assert output["count"] == 4


# Splitting by bytes


def test_bytes_mode_cuts_every_chunk_but_the_last_at_exactly_chunk_bytes(
    client: Any,
    stubber: Any,
) -> None:
    content = b"0123456789"
    expect_head(stubber, len(content))
    expect_get(stubber, content)

    for index, part in enumerate((b"0123", b"4567", b"89")):
        expect_put(stubber, index, part)

    output = TOOL["split"](client, plan(mode="bytes", chunk_bytes=4), read_bytes=3)

    assert output == {
        "chunks": [chunk(0, 4), chunk(1, 4), chunk(2, 2)],
        "count": 3,
        "source": source(10),
    }


def test_a_source_needing_more_than_max_chunks_bytes_is_refused_without_reading_it(
    client: Any,
    stubber: Any,
) -> None:
    expect_head(stubber, 10)

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan(mode="bytes", chunk_bytes=4, max_chunks=2))

    assert failure(raised) == (
        1,
        f"split_s3_object would split {SOURCE_URI} into 3 chunks, more than its max_chunks of 2.",
    )
    assert_documented(
        failure(raised)[1],
        {SOURCE_URI: "<URI>", "into 3": "into <COUNT>", "of 2": "of <MAX_CHUNKS>"},
    )


@pytest.mark.parametrize("mode", ["lines", "bytes"])
def test_an_empty_source_has_no_chunks_and_is_never_read(
    client: Any,
    stubber: Any,
    mode: str,
) -> None:
    expect_head(stubber, 0)

    output = TOOL["split"](client, plan(mode=mode))

    assert output == {"chunks": [], "count": 0, "source": source(0)}


# The source's version


def test_a_versioned_source_is_read_by_its_version_and_reports_it(
    client: Any,
    stubber: Any,
) -> None:
    content = b"one\ntwo\n"
    expect_head(stubber, len(content), version_id=VERSION_ID)
    expect_get(stubber, content, version_id=VERSION_ID)
    expect_get(stubber, content, version_id=VERSION_ID)
    expect_put(stubber, 0, content)

    output = TOOL["split"](client, plan())

    assert output["source"] == source(len(content), version_id=VERSION_ID)


def test_a_source_changed_between_the_two_reads_is_refused(
    client: Any,
    stubber: Any,
) -> None:
    content = b"one\ntwo\n"
    expect_head(stubber, len(content))
    expect_get(stubber, content)
    stubber.add_client_error(
        "get_object",
        service_error_code="PreconditionFailed",
        service_message="At least one of the pre-conditions you specified did not hold",
        http_status_code=412,
        expected_params={"Bucket": SOURCE_BUCKET, "Key": SOURCE_KEY, "IfMatch": ETAG},
    )

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan())

    assert failure(raised) == (1, f"split_s3_object found {SOURCE_URI} changed while splitting it.")
    assert_documented(failure(raised)[1], {SOURCE_URI: "<URI>"})


def test_lines_shorter_than_their_size_are_refused_before_anything_is_written(
    client: Any,
    stubber: Any,
) -> None:
    expect_head(stubber, 10)
    expect_get(stubber, b"one\ntwo\n")

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan(chunk_bytes=8))

    assert failure(raised) == (1, f"split_s3_object found {SOURCE_URI} changed while splitting it.")


@pytest.mark.parametrize(
    ("size", "content", "written"),
    [
        pytest.param(10, b"0123456", (b"0123",), id="shorter"),
        pytest.param(6, b"0123456", (b"0123", b"45"), id="longer"),
    ],
)
def test_bytes_that_differ_from_their_size_are_refused_once_found(
    client: Any,
    stubber: Any,
    size: int,
    content: bytes,
    written: tuple[bytes, ...],
) -> None:
    #
    # Bytes mode reads the source once, so the chunks before the difference
    # are already written; the step fails, and a retry writes a new folder.
    #
    expect_head(stubber, size)
    expect_get(stubber, content)

    for index, part in enumerate(written):
        expect_put(stubber, index, part)

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan(mode="bytes", chunk_bytes=4))

    assert failure(raised) == (1, f"split_s3_object found {SOURCE_URI} changed while splitting it.")


def test_chunks_carry_the_sources_content_type(
    client: Any,
    stubber: Any,
) -> None:
    content = b"{}\n"
    expect_head(stubber, len(content), content_type="application/x-ndjson")
    expect_get(stubber, content)
    expect_get(stubber, content)
    expect_put(stubber, 0, content, content_type="application/x-ndjson")

    assert TOOL["split"](client, plan())["count"] == 1


# Where the chunks go


@pytest.mark.parametrize(
    ("destination", "prefix"),
    [
        ("s3://tenix-chunks/chunks/", FOLDER),
        ("s3://tenix-chunks/chunks", FOLDER),
        ("s3://tenix-chunks/", f"{RUN_ID}/{STEP_ID}/1/"),
        ("s3://tenix-chunks", f"{RUN_ID}/{STEP_ID}/1/"),
    ],
)
def test_chunks_go_under_the_destination_in_the_folder_of_the_step_attempt(
    destination: str,
    prefix: str,
) -> None:
    planned = plan(destination_prefix=destination)

    assert (planned["destination_bucket"], planned["destination_prefix"]) == (
        DESTINATION_BUCKET,
        prefix,
    )


def test_a_retried_attempt_writes_a_folder_of_its_own() -> None:
    planned = TOOL["parse"](inputs(), lineage(attempt=2))

    assert planned["destination_prefix"] == f"chunks/{RUN_ID}/{STEP_ID}/2/"


def test_the_settings_default_to_five_mebibyte_chunks() -> None:
    assert TOOL["DEFAULT_CHUNK_BYTES"] == 5 * 1024 * 1024
    assert TOOL["MAX_CHUNK_BYTES"] == 100 * 1024 * 1024
    assert plan()["chunk_bytes"] == 5 * 1024 * 1024


# Failures of S3


def test_a_source_s3_refuses_to_read_is_reported_in_one_line(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_client_error(
        "head_object",
        service_error_code="404",
        service_message="Not Found",
        http_status_code=404,
        expected_params={"Bucket": SOURCE_BUCKET, "Key": SOURCE_KEY},
    )

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan())

    assert failure(raised) == (1, f"split_s3_object could not read {SOURCE_URI}: 404: Not Found.")
    assert_documented(
        failure(raised)[1], {SOURCE_URI: "<URI>", "404": "<CODE>", "Not Found": "<MESSAGE>"}
    )


def test_a_chunk_s3_refuses_to_write_is_reported_in_one_line(
    client: Any,
    stubber: Any,
) -> None:
    content = b"one\n"
    expect_head(stubber, len(content))
    expect_get(stubber, content)
    expect_get(stubber, content)
    stubber.add_client_error(
        "put_object",
        service_error_code="AccessDenied",
        service_message="Access Denied",
        http_status_code=403,
    )

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan())

    written = f"s3://{DESTINATION_BUCKET}/{FOLDER}chunk-000000"

    assert failure(raised) == (
        1,
        f"split_s3_object could not write {written}: AccessDenied: Access Denied.",
    )
    assert_documented(
        failure(raised)[1],
        {written: "<URI>", "AccessDenied": "<CODE>", "Access Denied": "<MESSAGE>"},
    )


def test_missing_credentials_are_reported_in_one_line(
    client: Any,
) -> None:
    def refuse(
        **parameters: Any,
    ) -> Any:
        """Fail as a client with no credentials does."""

        raise importlib.import_module("botocore.exceptions").NoCredentialsError()

    client.head_object = refuse

    with pytest.raises(FAILURE) as raised:
        TOOL["split"](client, plan())

    assert failure(raised) == (
        1,
        f"split_s3_object could not read {SOURCE_URI}: Unable to locate credentials.",
    )
    assert_documented(
        failure(raised)[1], {SOURCE_URI: "<URI>", "Unable to locate credentials": "<REASON>"}
    )


def test_without_boto3_the_tool_names_the_extra_that_installs_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(FAILURE) as raised:
        TOOL["open_client"]()

    assert failure(raised) == (
        1,
        "split_s3_object needs boto3, which is not installed; install azathoth-ai[worker].",
    )
    assert_documented(failure(raised)[1], {})


def test_without_boto3_the_tool_process_fails_with_that_message(
    tmp_path: Path,
) -> None:
    #
    # A boto3 that cannot be imported, ahead of the installed one.
    #
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "boto3.py").write_text('raise ImportError("No module named boto3")\n')
    tool = tmp_path / "tool"
    tool.write_text(standard_implementation("split_s3_object").source, encoding="utf-8")

    completed = subprocess.run(
        (sys.executable, str(tool)),
        input=json.dumps(inputs()).encode("utf-8"),
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(shadow), "AZATHOTH_LINEAGE": lineage()},
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stderr.decode("utf-8") == (
        "split_s3_object needs boto3, which is not installed; install azathoth-ai[worker]."
    )
    assert completed.stdout == b""


# Refusals of the tool's inputs, through the process runtime

REFUSALS: tuple[tuple[dict[str, JsonValue], str], ...] = (
    (
        {"uri": SOURCE_URI},
        "split_s3_object needs 'settings' to be an object.",
    ),
    (
        {**inputs(), "uri": "https://tenix-work/inbox/large.txt"},
        "split_s3_object needs 'uri' to be an s3:// URI naming an object.",
    ),
    (
        {**inputs(), "uri": "s3://tenix-work/"},
        "split_s3_object needs 'uri' to be an s3:// URI naming an object.",
    ),
    (
        inputs(destination_prefix="/tmp/chunks"),
        "split_s3_object needs 'destination_prefix' to be an s3:// URI naming a bucket.",
    ),
    (
        inputs(destination_prefix="s3:///chunks"),
        "split_s3_object needs 'destination_prefix' to be an s3:// URI naming a bucket.",
    ),
    (
        inputs(mode="words"),
        "split_s3_object needs 'mode' to be 'lines' or 'bytes'.",
    ),
    (
        inputs(chunk_bytes=0),
        "split_s3_object needs 'chunk_bytes' to be a whole number from 1 to 104857600.",
    ),
    (
        inputs(chunk_bytes=104857601),
        "split_s3_object needs 'chunk_bytes' to be a whole number from 1 to 104857600.",
    ),
    (
        inputs(chunk_bytes=True),
        "split_s3_object needs 'chunk_bytes' to be a whole number from 1 to 104857600.",
    ),
    (
        inputs(max_chunks=None),
        "split_s3_object needs 'max_chunks' to be a whole number of at least 1.",
    ),
    (
        inputs(max_chunks=0),
        "split_s3_object needs 'max_chunks' to be a whole number of at least 1.",
    ),
    (
        inputs(),
        "split_s3_object writes chunks only from a workflow step, and was not run in one.",
    ),
)


@pytest.mark.parametrize(
    ("given", "message"),
    [pytest.param(*refusal, id=f"{index}") for index, refusal in enumerate(REFUSALS)],
)
def test_bad_inputs_and_a_run_outside_a_step_are_refused_with_status_2(
    given: dict[str, JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("split_s3_object", given) == (2, message)
    assert_documented(message, {})


def test_a_chunk_bytes_of_exactly_the_maximum_is_accepted() -> None:
    assert plan(chunk_bytes=104857600)["chunk_bytes"] == 104857600


# The document and its README


def test_the_tool_grants_itself_only_the_aws_variables() -> None:
    implementation = standard_implementation("split_s3_object")

    assert implementation.environment == ("AWS_*",)
    assert implementation.timeout_seconds == 3600


def test_the_schema_states_the_scripts_modes_and_limits() -> None:
    schema: Any = standard_document("split_s3_object").definition.input_schema.json_schema
    settings = schema["properties"]["settings"]

    assert tuple(settings["properties"]["mode"]["enum"]) == TOOL["MODES"]
    assert settings["properties"]["chunk_bytes"]["maximum"] == TOOL["MAX_CHUNK_BYTES"]
    assert settings["required"] == ["destination_prefix", "max_chunks"]


def test_the_readme_documents_exactly_the_tools_messages() -> None:
    text = STANDARD_README.read_text(encoding="utf-8")
    section = text[text.index("### split_s3_object") : text.index("## Installing")]
    documented = {
        line
        for block in section.split("```text\n")[1:]
        for line in block.split("```", 1)[0].splitlines()
    }

    assert documented == set(DOCUMENTED)

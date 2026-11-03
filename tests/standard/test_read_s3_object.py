"""Tests for `read_s3_object`: one S3 object read within a cap, and decoded (ADR 0110).

The tool's script keeps its work in functions that take an S3 client, so
these tests load its source and call them with a real client answered by
botocore's `Stubber`; nothing reaches AWS. Its refusals of bad inputs run
through the real process runtime. boto3 ships no types, so it is imported
by name, and the tests that need it are skipped where it is not installed.
"""

import hashlib
import importlib
import io
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import JsonValue

from azathoth.inputs import InputContentError, decode_content
from tests.standard.harness import (
    standard_document,
    standard_implementation,
    standard_tool_failure,
)

PROJECT_ROOT = Path(__file__).parents[2]

STANDARD_README = PROJECT_ROOT / "src" / "azathoth" / "standard" / "README.md"

BUCKET = "tenix-work"

KEY = "chunks/run/step/1/chunk-000003"

URI = f"s3://{BUCKET}/{KEY}"

ETAG = '"d41d8cd98f00b204e9800998ecf8427e"'

#
# Every message the README documents for the tool, with its placeholders.
#
DOCUMENTED = (
    "read_s3_object needs 'settings' to be an object.",
    "read_s3_object needs 'uri' to be an s3:// URI naming an object.",
    "read_s3_object needs 'media_type' to be application/json or a text/* media type, "
    "lowercase and with no parameters.",
    "read_s3_object needs 'max_bytes' to be a whole number from 1 to 104857600.",
    "read_s3_object needs boto3, which is not installed; install azathoth-ai[worker].",
    "read_s3_object could not read <URI>: <CODE>: <MESSAGE>.",
    "read_s3_object could not read <URI>: <REASON>.",
    "read_s3_object found <URI> larger than its max_bytes of <MAX_BYTES>.",
    "read_s3_object found <URI> is not valid UTF-8: <REASON> at byte <BYTE>.",
    "read_s3_object found <URI> is not valid JSON: <REASON>.",
)


def script() -> dict[str, Any]:
    """Load the tool's source as a module that does not run, and return its names."""

    namespace: dict[str, Any] = {"__name__": "read_s3_object"}
    source = standard_implementation("read_s3_object").source

    exec(compile(source, "read_s3_object", "exec"), namespace)

    return namespace


TOOL = script()
"""The tool's functions and constants, loaded once."""

FAILURE: type[Exception] = TOOL["Failure"]
"""What the tool raises for every failure it reports."""


def inputs(
    **settings: JsonValue,
) -> dict[str, JsonValue]:
    """Return the tool's inputs for the object, with some settings."""

    return {"settings": dict(settings), "uri": URI}


def plan(
    **settings: JsonValue,
) -> dict[str, Any]:
    """Return the tool's plan of a read of the object."""

    result: dict[str, Any] = TOOL["parse"](inputs(**settings))

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


def expect_get(
    stubber: Any,
    content: bytes,
    *,
    max_bytes: int = 10 * 1024 * 1024,
) -> None:
    """Expect the one ranged read of the object, answered with some content."""

    stubber.add_response(
        "get_object",
        {"Body": body(content), "ContentLength": len(content), "ETag": ETAG},
        {"Bucket": BUCKET, "Key": KEY, "Range": f"bytes=0-{max_bytes}"},
    )


def output(
    value: JsonValue,
    content: bytes,
    media_type: str = "text/plain",
) -> dict[str, JsonValue]:
    """Return the tool's output for some content."""

    return {
        "value": value,
        "media_type": media_type,
        "size_bytes": len(content),
        "digest": hashlib.sha256(content).hexdigest(),
        "etag": ETAG.strip('"'),
    }


# Reading and decoding


def test_text_is_read_with_one_ranged_get_and_returned_as_a_string(
    client: Any,
    stubber: Any,
) -> None:
    content = "The old ones wait.\nThey wait in 灯台.\n".encode()
    expect_get(stubber, content)

    assert TOOL["read"](client, plan()) == output(content.decode(), content)


def test_json_is_parsed(
    client: Any,
    stubber: Any,
) -> None:
    content = b'{"claims": [1, 2, 3]}'
    expect_get(stubber, content)

    assert TOOL["read"](client, plan(media_type="application/json")) == output(
        {"claims": [1, 2, 3]}, content, "application/json"
    )


@pytest.mark.parametrize(
    ("content", "media_type"),
    [
        (b"\xef\xbb\xbfwith a byte order mark", "text/markdown"),
        (b'\xef\xbb\xbf["a", 1.5, null]', "application/json"),
        (b"", "text/plain"),
        ("plain é".encode(), "text/csv"),
    ],
)
def test_content_decodes_exactly_as_a_resolved_input_does(
    client: Any,
    stubber: Any,
    content: bytes,
    media_type: str,
) -> None:
    expect_get(stubber, content)

    value = TOOL["read"](client, plan(media_type=media_type))["value"]

    assert value == decode_content(content, media_type)


def test_the_default_is_ten_mebibytes_of_text() -> None:
    assert (plan()["media_type"], plan()["max_bytes"]) == ("text/plain", 10 * 1024 * 1024)
    assert TOOL["MAX_BYTES"] == 100 * 1024 * 1024


def test_settings_may_be_left_out() -> None:
    assert TOOL["parse"]({"uri": URI})["max_bytes"] == 10 * 1024 * 1024


def test_an_object_of_exactly_max_bytes_is_read(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, b"12345", max_bytes=5)

    assert TOOL["read"](client, plan(max_bytes=5))["value"] == "12345"


def test_an_object_larger_than_max_bytes_is_refused_from_the_byte_past_the_cap(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, b"123456", max_bytes=5)

    with pytest.raises(FAILURE) as raised:
        TOOL["read"](client, plan(max_bytes=5))

    assert failure(raised) == (1, f"read_s3_object found {URI} larger than its max_bytes of 5.")
    assert_documented(failure(raised)[1], {URI: "<URI>", "of 5": "of <MAX_BYTES>"})


def test_an_empty_object_is_read_again_plainly_for_its_etag(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_client_error(
        "get_object",
        service_error_code="InvalidRange",
        service_message="The requested range is not satisfiable",
        http_status_code=416,
        expected_params={"Bucket": BUCKET, "Key": KEY, "Range": "bytes=0-10485760"},
    )
    stubber.add_response(
        "get_object",
        {"Body": body(b""), "ContentLength": 0, "ETag": ETAG},
        {"Bucket": BUCKET, "Key": KEY},
    )

    assert TOOL["read"](client, plan()) == output("", b"")


def test_a_plain_read_s3_refuses_is_reported_whatever_its_code(
    client: Any,
    stubber: Any,
) -> None:
    for _ in range(2):
        stubber.add_client_error(
            "get_object",
            service_error_code="InvalidRange",
            service_message="The requested range is not satisfiable",
            http_status_code=416,
        )

    with pytest.raises(FAILURE) as raised:
        TOOL["read"](client, plan())

    assert failure(raised) == (
        1,
        f"read_s3_object could not read {URI}: InvalidRange: "
        "The requested range is not satisfiable.",
    )


# Content that does not decode


def test_content_that_is_not_utf8_is_refused(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, b"ok \xff")

    with pytest.raises(FAILURE) as raised:
        TOOL["read"](client, plan())

    assert failure(raised) == (
        1,
        f"read_s3_object found {URI} is not valid UTF-8: invalid start byte at byte 3.",
    )
    assert_documented(
        failure(raised)[1],
        {URI: "<URI>", "invalid start byte": "<REASON>", "byte 3": "byte <BYTE>"},
    )


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b'{"claims": ', "Expecting value"),
        (b"[NaN]", "NaN is not a JSON number"),
        (b"", "Expecting value"),
    ],
)
def test_content_that_is_not_json_is_refused(
    client: Any,
    stubber: Any,
    content: bytes,
    reason: str,
) -> None:
    if content:
        expect_get(stubber, content)
    else:
        stubber.add_client_error(
            "get_object",
            service_error_code="InvalidRange",
            http_status_code=416,
        )
        stubber.add_response("get_object", {"Body": body(b""), "ETag": ETAG})

    with pytest.raises(FAILURE) as raised:
        TOOL["read"](client, plan(media_type="application/json"))

    assert failure(raised) == (1, f"read_s3_object found {URI} is not valid JSON: {reason}.")
    assert_documented(failure(raised)[1], {URI: "<URI>", reason: "<REASON>"})

    with pytest.raises(InputContentError):
        decode_content(content, "application/json")


# Failures of S3


def test_an_object_s3_refuses_to_read_is_reported_in_one_line(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_client_error(
        "get_object",
        service_error_code="NoSuchKey",
        service_message="The specified key does not exist.",
        http_status_code=404,
    )

    with pytest.raises(FAILURE) as raised:
        TOOL["read"](client, plan())

    assert failure(raised) == (
        1,
        f"read_s3_object could not read {URI}: NoSuchKey: The specified key does not exist.",
    )
    assert_documented(
        failure(raised)[1],
        {URI: "<URI>", "NoSuchKey": "<CODE>", "The specified key does not exist": "<MESSAGE>"},
    )


def test_missing_credentials_are_reported_in_one_line(
    client: Any,
) -> None:
    def refuse(
        **parameters: Any,
    ) -> Any:
        """Fail as a client with no credentials does."""

        raise importlib.import_module("botocore.exceptions").NoCredentialsError()

    client.get_object = refuse

    with pytest.raises(FAILURE) as raised:
        TOOL["read"](client, plan())

    assert failure(raised) == (
        1,
        f"read_s3_object could not read {URI}: Unable to locate credentials.",
    )
    assert_documented(
        failure(raised)[1], {URI: "<URI>", "Unable to locate credentials": "<REASON>"}
    )


def test_without_boto3_the_tool_names_the_extra_that_installs_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(FAILURE) as raised:
        TOOL["open_client"]()

    assert failure(raised) == (
        1,
        "read_s3_object needs boto3, which is not installed; install azathoth-ai[worker].",
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
    tool.write_text(standard_implementation("read_s3_object").source, encoding="utf-8")

    completed = subprocess.run(
        (sys.executable, str(tool)),
        input=json.dumps(inputs()).encode("utf-8"),
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(shadow)},
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stderr.decode("utf-8") == (
        "read_s3_object needs boto3, which is not installed; install azathoth-ai[worker]."
    )
    assert completed.stdout == b""


# Refusals of the tool's inputs, through the process runtime

MEDIA_TYPE_REFUSAL = (
    "read_s3_object needs 'media_type' to be application/json or a text/* media type, "
    "lowercase and with no parameters."
)

MAX_BYTES_REFUSAL = "read_s3_object needs 'max_bytes' to be a whole number from 1 to 104857600."

URI_REFUSAL = "read_s3_object needs 'uri' to be an s3:// URI naming an object."

REFUSALS: tuple[tuple[dict[str, JsonValue], str], ...] = (
    ({"settings": [], "uri": URI}, "read_s3_object needs 'settings' to be an object."),
    ({"settings": {}}, URI_REFUSAL),
    ({"settings": {}, "uri": "file:///etc/hostname"}, URI_REFUSAL),
    ({"settings": {}, "uri": "s3://tenix-work"}, URI_REFUSAL),
    ({"settings": {}, "uri": "s3:///chunk-000000"}, URI_REFUSAL),
    (inputs(media_type="image/png"), MEDIA_TYPE_REFUSAL),
    (inputs(media_type="text/plain; charset=utf-8"), MEDIA_TYPE_REFUSAL),
    (inputs(media_type="Text/Plain"), MEDIA_TYPE_REFUSAL),
    (inputs(media_type=1), MEDIA_TYPE_REFUSAL),
    (inputs(max_bytes=0), MAX_BYTES_REFUSAL),
    (inputs(max_bytes=104857601), MAX_BYTES_REFUSAL),
    (inputs(max_bytes=True), MAX_BYTES_REFUSAL),
)


@pytest.mark.parametrize(
    ("given", "message"),
    [pytest.param(*refusal, id=f"{index}") for index, refusal in enumerate(REFUSALS)],
)
def test_bad_inputs_are_refused_with_status_2(
    given: dict[str, JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("read_s3_object", given) == (2, message)
    assert_documented(message, {})


def test_a_max_bytes_of_exactly_the_maximum_is_accepted() -> None:
    assert plan(max_bytes=104857600)["max_bytes"] == 104857600


# The document and its README


def test_the_tool_grants_itself_only_the_aws_variables() -> None:
    implementation = standard_implementation("read_s3_object")

    assert implementation.environment == ("AWS_*",)
    assert implementation.timeout_seconds == 300


def test_the_schema_states_the_scripts_limit() -> None:
    schema: Any = standard_document("read_s3_object").definition.input_schema.json_schema

    assert (
        schema["properties"]["settings"]["properties"]["max_bytes"]["maximum"]
        == (TOOL["MAX_BYTES"])
    )
    assert schema["required"] == ["uri"]


def test_the_readme_documents_exactly_the_tools_messages() -> None:
    text = STANDARD_README.read_text(encoding="utf-8")
    section = text[text.index("### read_s3_object") : text.index("## Installing")]
    documented = {
        line
        for block in section.split("```text\n")[1:]
        for line in block.split("```", 1)[0].splitlines()
    }

    assert documented == set(DOCUMENTED)

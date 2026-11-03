"""Tests that ADR 0108 states `s3://` inputs and the S3 store as they really behave."""

import importlib
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from azathoth.cli import build_parser
from azathoth.cli.worker import MAX_WORKER_INPUT_BYTES
from azathoth.inputs import (
    CONTENT_STORE_VARIABLE,
    DEFAULT_MAX_INPUT_BYTES,
    MISSING_S3_EXTRA_MESSAGE,
    InputResolutionError,
    S3ContentLocation,
    S3InputLocation,
    S3InputResolver,
)

ADR = Path(__file__).parents[2] / "docs" / "adrs" / "0108-read-inputs-from-s3.md"

URI = "s3://azathoth-inputs/requests/review.json"

ALLOWED = (S3InputLocation.parse("azathoth-inputs/requests/"),)


def text() -> str:
    """Return the ADR."""

    return ADR.read_text(encoding="utf-8")


def prose() -> str:
    """Return the ADR with its lines joined, as it reads."""

    return " ".join(text().split())


def assert_quoted(
    message: str,
) -> None:
    """Check the ADR quotes one message as a whole `text` block."""

    assert f"```text\n{message}\n" in text() or f"\n{message}\n```" in text(), message


@pytest.fixture
def stubber() -> Iterator[Any]:
    """Return a Stubber over a real S3 client with fixed credentials."""

    pytest.importorskip("boto3")

    client = (
        importlib.import_module("boto3")
        .session.Session()
        .client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
    )
    stubber_type = importlib.import_module("botocore.stub").Stubber

    with stubber_type(client) as active:
        active.client = client
        yield active


def refusal(
    resolver: S3InputResolver,
    uri: str = URI,
) -> str:
    """Return the refusal one read raises."""

    with pytest.raises(InputResolutionError) as raised:
        resolver.read(uri, max_bytes=1024)

    return str(raised.value)


def test_the_adr_quotes_the_real_refusal_outside_the_allowed_locations() -> None:
    assert_quoted(refusal(S3InputResolver(ALLOWED), "s3://azathoth-other/requests/review.json"))


@pytest.mark.parametrize(
    ("code", "message", "status"),
    [("NoSuchKey", "", 404), ("AccessDenied", "Access Denied", 403)],
)
def test_the_adr_quotes_the_real_refusals_of_s3(
    stubber: Any,
    code: str,
    message: str,
    status: int,
) -> None:
    stubber.add_client_error(
        "get_object",
        service_error_code=code,
        service_message=message,
        http_status_code=status,
    )

    assert_quoted(refusal(S3InputResolver(ALLOWED, client=stubber.client)))


def test_the_adr_quotes_the_real_missing_extra_message() -> None:
    assert_quoted(MISSING_S3_EXTRA_MESSAGE)


def test_the_adr_states_the_real_caps() -> None:
    assert DEFAULT_MAX_INPUT_BYTES == 10 * 1024 * 1024
    assert MAX_WORKER_INPUT_BYTES == 100 * 1024 * 1024
    assert "10 MiB by default, from 1 byte to 100 MiB" in prose()


def test_the_adr_names_the_real_options_and_variable() -> None:
    run = build_parser().parse_args(
        (
            "worker",
            "run",
            "--queue-url",
            "https://sqs.us-east-1.amazonaws.com/1/q",
            "--allow-input-bucket",
            "azathoth-inputs/requests/",
            "--max-input-bytes",
            "1",
        )
    )

    assert run.worker_allow_input_buckets == ["azathoth-inputs/requests/"]
    assert "`azathoth worker run --allow-input-bucket <BUCKET>[/<PREFIX>]`" in prose()
    assert "`--max-input-bytes`" in prose()
    assert f"`{CONTENT_STORE_VARIABLE}=s3://<BUCKET>[/<PREFIX>]`" in prose()


def test_the_adr_states_where_content_is_kept() -> None:
    location = S3ContentLocation.parse("s3://azathoth-content/evidence")

    assert location.key("<DIGEST>") == "evidence/sha256/<DIGEST>"
    assert "`<PREFIX>/sha256/<DIGEST>`" in prose()


def test_the_adr_states_how_a_prefix_is_matched() -> None:
    literal = S3InputLocation.parse("azathoth-inputs/requests")

    assert literal.allows("azathoth-inputs", "requests-old/review.json")
    assert re.search(r"`requests` allowing `requests-old/`", prose())

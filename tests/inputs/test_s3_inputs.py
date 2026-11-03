"""Tests for `s3://` input references from allow-listed buckets (ADR 0108).

The resolver's reads need boto3, so those tests are skipped where the
`worker` extra is not installed. They never reach AWS: botocore's `Stubber`
answers every call. boto3 ships no types, so it is imported by name.
"""

import importlib
import io
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from azathoth.inputs import (
    MISSING_S3_EXTRA_MESSAGE,
    S3_SCHEME,
    InputPolicy,
    InputResolutionError,
    InputResolver,
    InputUnavailableError,
    ReferenceInput,
    S3InputLocation,
    S3InputResolver,
    SQLiteContentStore,
    content_bytes_digest,
    resolve_input,
    s3_object,
)

BUCKET = "azathoth-inputs"

URI = f"s3://{BUCKET}/requests/chapter-12.md"

CHAPTER = b"# Chapter 12\n\nThe old ones wait.\n"


def location(
    value: str,
) -> S3InputLocation:
    """Return one allowed location."""

    return S3InputLocation.parse(value)


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
    key: str = "requests/chapter-12.md",
    max_bytes: int = 1024,
) -> None:
    """Expect one ranged read of an object, answered with some content."""

    stubber.add_response(
        "get_object",
        {"Body": body(content), "ContentLength": len(content)},
        {"Bucket": BUCKET, "Key": key, "Range": f"bytes=0-{max_bytes}"},
    )


def resolver(
    client: Any,
    *allowed: str,
) -> S3InputResolver:
    """Return a resolver over the stubbed client, allowing some locations."""

    return S3InputResolver(
        tuple(location(value) for value in allowed or (BUCKET,)),
        client=client,
    )


# URIs


def test_an_s3_uri_names_a_bucket_and_a_key() -> None:
    assert S3_SCHEME == "s3"
    assert s3_object(URI) == (BUCKET, "requests/chapter-12.md")
    assert s3_object("s3://azathoth-inputs/a b/ü.md") == (BUCKET, "a b/ü.md")


@pytest.mark.parametrize(
    ("uri", "message"),
    [
        ("file:///tmp/x.md", "Input file:///tmp/x.md is not an s3:// URI."),
        (
            "s3://azathoth-inputs",
            "Input s3://azathoth-inputs must name a bucket and an object key.",
        ),
        (
            "s3://azathoth-inputs/",
            "Input s3://azathoth-inputs/ must name a bucket and an object key.",
        ),
        (
            "s3://azathoth-inputs/x.md?versionId=3",
            "Input s3://azathoth-inputs/x.md?versionId=3 must name an object only, "
            "with no query or fragment.",
        ),
        (
            "s3://azathoth-inputs/x.md#part",
            "Input s3://azathoth-inputs/x.md#part must name an object only, "
            "with no query or fragment.",
        ),
    ],
)
def test_an_s3_uri_that_names_no_object_is_refused(
    uri: str,
    message: str,
) -> None:
    with pytest.raises(InputResolutionError) as raised:
        s3_object(uri)

    assert str(raised.value) == message


# Allowed locations


def test_a_bare_bucket_allows_every_key_in_it() -> None:
    allowed = location(BUCKET)

    assert (allowed.bucket, allowed.prefix) == (BUCKET, "")
    assert str(allowed) == BUCKET
    assert allowed.allows(BUCKET, "anything/at/all.json")
    assert not allowed.allows("azathoth-other", "anything/at/all.json")


def test_a_prefix_allows_only_the_keys_that_start_with_it() -> None:
    allowed = location(f"{BUCKET}/requests/")

    assert (allowed.bucket, allowed.prefix) == (BUCKET, "requests/")
    assert str(allowed) == f"{BUCKET}/requests/"
    assert allowed.allows(BUCKET, "requests/chapter-12.md")
    assert not allowed.allows(BUCKET, "requests-old/chapter-12.md")
    assert not allowed.allows(BUCKET, "secrets/key.pem")


def test_a_prefix_is_matched_literally() -> None:
    allowed = location(f"{BUCKET}/requests")

    assert allowed.allows(BUCKET, "requests/chapter-12.md")
    assert allowed.allows(BUCKET, "requests-old/chapter-12.md")
    assert not allowed.allows(BUCKET, "../requests/chapter-12.md")


@pytest.mark.parametrize(
    "value",
    ["", "Azathoth-Inputs", "ab", "-azathoth", "azathoth-", "azathoth_inputs", "/requests/"],
)
def test_a_location_must_start_with_a_valid_bucket_name(
    value: str,
) -> None:
    with pytest.raises(ValueError) as raised:
        S3InputLocation.parse(value)

    assert str(raised.value) == (
        f"{value!r} is not an S3 bucket, or a bucket and a key prefix: "
        "a bucket name is 3 to 63 lowercase letters, digits, dots and hyphens."
    )


# Reading


def test_the_resolver_is_an_input_resolver(
    client: Any,
) -> None:
    assert isinstance(resolver(client), InputResolver)


def test_an_allowed_object_is_read_with_one_ranged_get(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, CHAPTER)

    assert resolver(client).read(URI, max_bytes=1024) == CHAPTER


def test_an_object_beyond_the_cap_is_refused_without_reading_it_all(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, b"x" * 9, max_bytes=8)

    with pytest.raises(InputResolutionError) as raised:
        resolver(client).read(URI, max_bytes=8)

    assert str(raised.value) == f"Input {URI} is larger than the limit of 8 bytes."


def test_an_empty_object_reads_as_no_bytes(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_client_error(
        "get_object",
        service_error_code="InvalidRange",
        service_message="The requested range is not satisfiable",
        http_status_code=416,
        expected_params={
            "Bucket": BUCKET,
            "Key": "requests/chapter-12.md",
            "Range": "bytes=0-1024",
        },
    )

    assert resolver(client).read(URI, max_bytes=1024) == b""


def test_an_object_outside_the_allowed_locations_is_refused_without_a_call(
    client: Any,
    stubber: Any,
) -> None:
    uri = "s3://azathoth-other/requests/chapter-12.md"

    with pytest.raises(InputResolutionError) as raised:
        resolver(client, f"{BUCKET}/requests/", f"{BUCKET}/batches/").read(uri, max_bytes=1024)

    assert str(raised.value) == (
        f"Input {uri} is not in an allowed location; "
        f"allowed: {BUCKET}/requests/, {BUCKET}/batches/."
    )


def test_an_object_outside_an_allowed_prefix_is_refused(
    client: Any,
    stubber: Any,
) -> None:
    uri = f"s3://{BUCKET}/secrets/key.pem"

    with pytest.raises(InputResolutionError) as raised:
        resolver(client, f"{BUCKET}/requests/").read(uri, max_bytes=1024)

    assert str(raised.value) == (
        f"Input {uri} is not in an allowed location; allowed: {BUCKET}/requests/."
    )


def test_a_resolver_with_no_locations_allows_nothing() -> None:
    with pytest.raises(InputResolutionError) as raised:
        S3InputResolver(()).read(URI, max_bytes=1024)

    assert str(raised.value) == f"Input {URI} is not in an allowed location; allowed: none."


@pytest.mark.parametrize("code", ["NoSuchKey", "NoSuchBucket"])
def test_a_missing_object_does_not_exist(
    client: Any,
    stubber: Any,
    code: str,
) -> None:
    stubber.add_client_error("get_object", service_error_code=code, http_status_code=404)

    with pytest.raises(InputResolutionError) as raised:
        resolver(client).read(URI, max_bytes=1024)

    assert str(raised.value) == f"Input {URI} does not exist."


def test_an_object_the_worker_may_not_read_says_what_s3_said(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_client_error(
        "get_object",
        service_error_code="AccessDenied",
        service_message="Access Denied",
        http_status_code=403,
    )

    with pytest.raises(InputResolutionError) as raised:
        resolver(client).read(URI, max_bytes=1024)

    assert str(raised.value) == f"Unable to read input {URI}: AccessDenied: Access Denied"


def test_a_read_that_never_reached_s3_is_not_the_requests_fault(
    client: Any,
) -> None:
    botocore_exceptions = importlib.import_module("botocore.exceptions")

    def unreachable(
        **_: object,
    ) -> None:
        raise botocore_exceptions.NoCredentialsError()

    client.get_object = unreachable

    with pytest.raises(InputUnavailableError) as raised:
        resolver(client).read(URI, max_bytes=1024)

    assert not isinstance(raised.value, InputResolutionError)
    assert str(raised.value) == (
        f"Unable to reach S3 for input {URI}: NoCredentialsError: Unable to locate credentials"
    )


def test_without_boto3_reading_says_which_extra_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(InputUnavailableError) as raised:
        S3InputResolver((location(BUCKET),)).read(URI, max_bytes=1024)

    assert str(raised.value) == MISSING_S3_EXTRA_MESSAGE
    assert MISSING_S3_EXTRA_MESSAGE == (
        "s3:// inputs need boto3, which is not installed; install azathoth-ai[worker]."
    )


def test_a_refused_location_never_needs_boto3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(InputResolutionError):
        S3InputResolver((location(BUCKET),)).read("s3://azathoth-other/x.md", max_bytes=1024)


def test_the_client_is_made_once_on_the_first_read(
    client: Any,
    stubber: Any,
) -> None:
    made: list[int] = []

    def make() -> Any:
        made.append(1)

        return client

    expect_get(stubber, CHAPTER)
    expect_get(stubber, CHAPTER)

    reader = S3InputResolver((location(BUCKET),), client_factory=make)

    assert made == []

    reader.read(URI, max_bytes=1024)
    reader.read(URI, max_bytes=1024)

    assert made == [1]


# Resolving


def test_an_s3_reference_resolves_with_its_provenance(
    client: Any,
    stubber: Any,
    tmp_path: Path,
) -> None:
    expect_get(stubber, CHAPTER, max_bytes=4096)
    store = SQLiteContentStore(tmp_path / "azathoth.db")

    resolved = resolve_input(
        ReferenceInput(uri=URI, media_type="text/markdown"),
        policy=InputPolicy(resolvers={S3_SCHEME: resolver(client)}, max_bytes=4096),
        store=store,
    )

    assert resolved.value == CHAPTER.decode()
    assert resolved.provenance is not None
    assert resolved.provenance.uri == URI
    assert resolved.provenance.size_bytes == len(CHAPTER)
    assert resolved.provenance.digest == content_bytes_digest(CHAPTER)
    assert store.get(content_bytes_digest(CHAPTER)) == CHAPTER


def test_an_s3_reference_that_does_not_decode_is_refused(
    client: Any,
    stubber: Any,
    tmp_path: Path,
) -> None:
    expect_get(stubber, b"not json", max_bytes=4096)

    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            ReferenceInput(uri=URI, media_type="application/json"),
            policy=InputPolicy(resolvers={S3_SCHEME: resolver(client)}, max_bytes=4096),
            store=SQLiteContentStore(tmp_path / "azathoth.db"),
        )

    assert str(raised.value).startswith(f"Input {URI}: Content is not valid JSON")

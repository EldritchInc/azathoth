"""Tests for keeping resolved content in Amazon S3 (ADR 0108).

The store's calls need boto3, so those tests are skipped where the `worker`
extra is not installed. They never reach AWS: botocore's `Stubber` answers
every call. boto3 ships no types, so it is imported by name.
"""

import importlib
import io
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from azathoth.inputs import (
    CONTENT_STORE_VARIABLE,
    MISSING_CONTENT_STORE_EXTRA_MESSAGE,
    ContentStore,
    ContentStoreError,
    S3ContentLocation,
    S3ContentStore,
    content_bytes_digest,
    content_store_location,
)

BUCKET = "azathoth-content"

CONTENT = b"the old ones wait"

DIGEST = content_bytes_digest(CONTENT)

KEY = f"evidence/sha256/{DIGEST}"


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


def store(
    client: Any,
    url: str = f"s3://{BUCKET}/evidence",
) -> S3ContentStore:
    """Return a store over the stubbed client."""

    return S3ContentStore(S3ContentLocation.parse(url), client=client)


def body(
    content: bytes,
) -> Any:
    """Return an object body as boto3 returns it."""

    streaming = importlib.import_module("botocore.response").StreamingBody

    return streaming(io.BytesIO(content), len(content))


# Where content goes


@pytest.mark.parametrize(
    ("url", "bucket", "prefix"),
    [
        (f"s3://{BUCKET}", BUCKET, ""),
        (f"s3://{BUCKET}/", BUCKET, ""),
        (f"s3://{BUCKET}/evidence", BUCKET, "evidence"),
        (f"s3://{BUCKET}/evidence/", BUCKET, "evidence"),
        (f"s3://{BUCKET}/azathoth/evidence", BUCKET, "azathoth/evidence"),
    ],
)
def test_a_content_store_url_names_a_bucket_and_a_prefix(
    url: str,
    bucket: str,
    prefix: str,
) -> None:
    location = S3ContentLocation.parse(url)

    assert (location.bucket, location.prefix) == (bucket, prefix)


def test_content_is_kept_under_its_digest() -> None:
    assert S3ContentLocation.parse(f"s3://{BUCKET}/evidence").key(DIGEST) == KEY
    assert S3ContentLocation.parse(f"s3://{BUCKET}").key(DIGEST) == f"sha256/{DIGEST}"


@pytest.mark.parametrize(
    "url",
    [
        "azathoth-content",
        "file:///tmp/content",
        "s3://",
        "s3://Not_A_Bucket/evidence",
        f"s3://{BUCKET}/evidence?versionId=1",
    ],
)
def test_a_content_store_url_that_is_not_s3_is_refused(
    url: str,
) -> None:
    with pytest.raises(ContentStoreError) as raised:
        S3ContentLocation.parse(url)

    assert str(raised.value) == (
        f"AZATHOTH_CONTENT_STORE {url!r} is not an s3://<BUCKET>[/<PREFIX>] URL."
    )


def test_the_environment_names_the_store_or_leaves_the_database_table() -> None:
    assert CONTENT_STORE_VARIABLE == "AZATHOTH_CONTENT_STORE"
    assert content_store_location({}) is None
    assert content_store_location({CONTENT_STORE_VARIABLE: ""}) is None
    assert content_store_location(
        {CONTENT_STORE_VARIABLE: f"s3://{BUCKET}/evidence"}
    ) == S3ContentLocation(bucket=BUCKET, prefix="evidence")


# The store


def test_the_store_is_a_content_store(
    client: Any,
) -> None:
    assert isinstance(store(client), ContentStore)


def test_put_writes_once_only_if_nothing_is_there_and_returns_the_digest(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_response(
        "put_object",
        {},
        {"Bucket": BUCKET, "Key": KEY, "Body": CONTENT, "IfNoneMatch": "*"},
    )

    assert store(client).put(CONTENT) == DIGEST


@pytest.mark.parametrize(
    ("code", "status"),
    [("PreconditionFailed", 412), ("ConditionalRequestConflict", 409)],
)
def test_content_already_stored_or_being_stored_is_not_written_again(
    client: Any,
    stubber: Any,
    code: str,
    status: int,
) -> None:
    stubber.add_client_error("put_object", service_error_code=code, http_status_code=status)

    assert store(client).put(CONTENT) == DIGEST


def test_a_refused_write_names_the_object_and_what_s3_said(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_client_error(
        "put_object",
        service_error_code="AccessDenied",
        service_message="Access Denied",
        http_status_code=403,
    )

    with pytest.raises(ContentStoreError) as raised:
        store(client).put(CONTENT)

    assert str(raised.value) == (
        f"Cannot store content in s3://{BUCKET}/{KEY}: AccessDenied: Access Denied"
    )


def test_a_write_that_never_reached_s3_names_botocores_error(
    client: Any,
) -> None:
    botocore_exceptions = importlib.import_module("botocore.exceptions")

    def unreachable(
        **_: object,
    ) -> None:
        raise botocore_exceptions.NoCredentialsError()

    client.put_object = unreachable

    with pytest.raises(ContentStoreError) as raised:
        store(client).put(CONTENT)

    assert str(raised.value) == (
        f"Cannot store content in s3://{BUCKET}/{KEY}: "
        "NoCredentialsError: Unable to locate credentials"
    )


def test_get_returns_the_stored_bytes(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_response("get_object", {"Body": body(CONTENT)}, {"Bucket": BUCKET, "Key": KEY})

    assert store(client).get(DIGEST) == CONTENT


def test_get_of_content_never_stored_is_none(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)

    assert store(client).get(DIGEST) is None


def test_contains_asks_s3_for_the_object(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_response("head_object", {}, {"Bucket": BUCKET, "Key": KEY})
    stubber.add_client_error("head_object", service_error_code="404", http_status_code=404)

    assert store(client).contains(DIGEST) is True
    assert store(client).contains(DIGEST) is False


def test_a_refused_read_names_the_object_and_what_s3_said(
    client: Any,
    stubber: Any,
) -> None:
    stubber.add_client_error(
        "head_object", service_error_code="403", service_message="Forbidden", http_status_code=403
    )

    with pytest.raises(ContentStoreError) as raised:
        store(client).contains(DIGEST)

    assert str(raised.value) == f"Cannot read s3://{BUCKET}/{KEY}: 403: Forbidden"


def test_without_boto3_the_store_says_which_extra_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(ContentStoreError) as raised:
        S3ContentStore(S3ContentLocation.parse(f"s3://{BUCKET}"))

    assert str(raised.value) == MISSING_CONTENT_STORE_EXTRA_MESSAGE
    assert MISSING_CONTENT_STORE_EXTRA_MESSAGE == (
        "AZATHOTH_CONTENT_STORE names S3, but boto3 is not installed; install azathoth-ai[worker]."
    )

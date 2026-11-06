"""Tests for recording the S3 object version an input was read from (ADR 0112).

The resolver's reads need boto3, so these tests are skipped where the
`worker` extra is not installed. They never reach AWS: botocore's `Stubber`
answers every call. boto3 ships no types, so it is imported by name.
"""

import importlib
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from azathoth.inputs import (
    S3_SCHEME,
    FileInputResolver,
    InMemoryContentStore,
    InputOrigin,
    InputPolicy,
    InputProvenance,
    InputResolutionError,
    ReferenceInput,
    S3InputLocation,
    S3InputResolver,
    VersionedContent,
    VersionedInputResolver,
    content_bytes_digest,
    resolve_input,
)
from azathoth.workflows import create_workflow_input_events

BUCKET = "claims-intake"

KEY = "2026/11/claim-0412.pdf"

URI = f"s3://{BUCKET}/{KEY}"

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

VERSION_ID = "3HL4kqtJlcpXroDTDmJ.rmSpXd3dIbrHY"

ETAG = "9b2cf535f27731c974343645a3985328"


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
    version_id: str | None = VERSION_ID,
    etag: str | None = ETAG,
    max_bytes: int | None = 1024,
) -> None:
    """Expect one read of the object, ranged unless `max_bytes` is None."""

    response: dict[str, Any] = {"Body": body(content), "ContentLength": len(content)}

    if version_id is not None:
        response["VersionId"] = version_id

    if etag is not None:
        response["ETag"] = f'"{etag}"'

    expected: dict[str, Any] = {"Bucket": BUCKET, "Key": KEY}

    if max_bytes is not None:
        expected["Range"] = f"bytes=0-{max_bytes}"

    stubber.add_response("get_object", response, expected)


def expect_empty_range(
    stubber: Any,
) -> None:
    """Expect the ranged read S3 refuses for an empty object."""

    stubber.add_client_error(
        "get_object",
        service_error_code="InvalidRange",
        service_message="The requested range is not satisfiable",
        http_status_code=416,
        expected_params={"Bucket": BUCKET, "Key": KEY, "Range": "bytes=0-1024"},
    )


def resolver(
    client: Any,
) -> S3InputResolver:
    """Return a resolver over the stubbed client, allowing the bucket."""

    return S3InputResolver((S3InputLocation.parse(BUCKET),), client=client)


def test_the_s3_resolver_reads_versions_and_the_file_resolver_does_not(
    client: Any,
) -> None:
    assert isinstance(resolver(client), VersionedInputResolver)
    assert not isinstance(FileInputResolver(), VersionedInputResolver)


def test_a_versioned_read_returns_the_version_and_etag_it_read(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, PDF)

    assert resolver(client).read_versioned(URI, max_bytes=1024) == VersionedContent(
        content=PDF,
        version_id=VERSION_ID,
        etag=ETAG,
    )


def test_an_unversioned_bucket_gives_only_an_etag(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, PDF, version_id=None)

    assert resolver(client).read_versioned(URI, max_bytes=1024) == VersionedContent(
        content=PDF,
        etag=ETAG,
    )


def test_a_plain_read_still_returns_only_the_bytes(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, PDF)

    assert resolver(client).read(URI, max_bytes=1024) == PDF


def test_an_empty_object_is_read_once_more_for_its_version(
    client: Any,
    stubber: Any,
) -> None:
    expect_empty_range(stubber)
    expect_get(stubber, b"", max_bytes=None)

    assert resolver(client).read_versioned(URI, max_bytes=1024) == VersionedContent(
        content=b"",
        version_id=VERSION_ID,
        etag=ETAG,
    )


def test_an_object_replaced_while_it_is_read_again_is_held_to_the_cap(
    client: Any,
    stubber: Any,
) -> None:
    expect_empty_range(stubber)
    expect_get(stubber, b"x" * 1025, max_bytes=None)

    with pytest.raises(InputResolutionError) as raised:
        resolver(client).read_versioned(URI, max_bytes=1024)

    assert str(raised.value) == f"Input {URI} is larger than the limit of 1024 bytes."


def test_an_object_replaced_while_it_is_read_again_keeps_its_own_version(
    client: Any,
    stubber: Any,
) -> None:
    expect_empty_range(stubber)
    expect_get(stubber, PDF, version_id="later", etag="feedface", max_bytes=None)

    assert resolver(client).read_versioned(URI, max_bytes=1024) == VersionedContent(
        content=PDF,
        version_id="later",
        etag="feedface",
    )


def test_an_s3_reference_records_the_version_it_was_read_from(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, PDF)
    store = InMemoryContentStore()

    resolved = resolve_input(
        ReferenceInput(uri=URI, media_type="application/pdf"),
        policy=InputPolicy(resolvers={S3_SCHEME: resolver(client)}, max_bytes=1024),
        store=store,
    )

    digest = content_bytes_digest(PDF)

    assert resolved.provenance == InputProvenance(
        uri=URI,
        origin=InputOrigin(uri=URI, version_id=VERSION_ID, etag=ETAG),
        media_type="application/pdf",
        size_bytes=len(PDF),
        digest=digest,
    )
    assert store.get(digest) == PDF


def test_an_s3_references_event_records_its_version(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, PDF, version_id=None)

    resolved = resolve_input(
        ReferenceInput(uri=URI, media_type="application/pdf"),
        policy=InputPolicy(resolvers={S3_SCHEME: resolver(client)}, max_bytes=1024),
        store=InMemoryContentStore(),
    )

    _, event = create_workflow_input_events(resolved, producer="azathoth.worker")

    assert event.payload == {
        "uri": URI,
        "origin": {"uri": URI, "etag": ETAG},
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
        "digest": content_bytes_digest(PDF),
    }


def test_a_read_with_neither_version_nor_etag_records_no_origin(
    client: Any,
    stubber: Any,
) -> None:
    expect_get(stubber, PDF, version_id=None, etag=None)

    resolved = resolve_input(
        ReferenceInput(uri=URI, media_type="application/pdf"),
        policy=InputPolicy(resolvers={S3_SCHEME: resolver(client)}, max_bytes=1024),
        store=InMemoryContentStore(),
    )

    assert resolved.provenance is not None
    assert resolved.provenance.origin is None


def test_a_file_reference_records_no_origin(
    tmp_path: Path,
) -> None:
    path = tmp_path / "claim.pdf"
    path.write_bytes(PDF)

    resolved = resolve_input(
        ReferenceInput(uri=path.as_uri(), media_type="application/pdf"),
        policy=InputPolicy(resolvers={"file": FileInputResolver()}),
        store=InMemoryContentStore(),
    )

    assert resolved.provenance is not None
    assert resolved.provenance.origin is None


def test_a_plain_read_refused_for_its_range_is_reported_as_s3_said(
    client: Any,
    stubber: Any,
) -> None:
    expect_empty_range(stubber)
    stubber.add_client_error(
        "get_object",
        service_error_code="InvalidRange",
        service_message="The requested range is not satisfiable",
        http_status_code=416,
        expected_params={"Bucket": BUCKET, "Key": KEY},
    )

    with pytest.raises(InputResolutionError) as raised:
        resolver(client).read_versioned(URI, max_bytes=1024)

    assert str(raised.value) == (
        f"Unable to read input {URI}: InvalidRange: The requested range is not satisfiable"
    )

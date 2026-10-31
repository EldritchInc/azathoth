"""Tests for job request digests (ADR 0097)."""

import hashlib
import json
from typing import Any
from uuid import UUID

import pytest

from azathoth.jobs import (
    decode_job_request,
    job_request_canonical_json,
    job_request_digest,
    parse_job_request,
)
from azathoth.workflows import REQUEST_DIGEST_PATTERN, InvocationIdempotency

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

OTHER_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

KEY = "order-4711-review"


def request_data(
    **changes: Any,
) -> dict[str, Any]:
    """Return one valid request document, with changes."""

    data: dict[str, Any] = {
        "kind": "invoke",
        "version": 1,
        "idempotency_key": KEY,
        "workflow_id": str(WORKFLOW_ID),
        "input": {"value": {"change": "rename", "files": ["a.py", "b.py"]}},
        "caller_metadata": {"ticket": "OPS-12"},
    }

    data.update(changes)

    return data


def digest(
    data: dict[str, Any],
) -> str:
    """Return the digest of one request document."""

    return job_request_digest(decode_job_request(data))


def test_the_canonical_form_is_sorted_compact_and_leaves_out_the_key() -> None:
    canonical = job_request_canonical_json(decode_job_request(request_data()))

    assert canonical == (
        '{"caller_metadata":{"ticket":"OPS-12"},'
        '"input":{"media_type":"application/json",'
        '"value":{"change":"rename","files":["a.py","b.py"]}},'
        '"kind":"invoke","version":1,'
        '"workflow_id":"11111111-1111-1111-1111-111111111111"}'
    )

    assert KEY not in canonical


def test_the_digest_is_the_sha256_of_the_canonical_form() -> None:
    request = decode_job_request(request_data())

    assert (
        job_request_digest(request)
        == hashlib.sha256(job_request_canonical_json(request).encode("utf-8")).hexdigest()
    )


def test_the_digest_is_one_an_invocation_can_record() -> None:
    InvocationIdempotency(key=KEY, request_digest=digest(request_data()))

    assert len(digest(request_data())) == 64
    assert REQUEST_DIGEST_PATTERN == r"^[0-9a-f]{64}$"


def test_the_digest_ignores_key_order_and_formatting() -> None:
    data = request_data()

    compact = json.dumps(data, separators=(",", ":"))
    spread = json.dumps(dict(reversed(list(data.items()))), indent=4)

    assert job_request_digest(parse_job_request(compact)) == job_request_digest(
        parse_job_request(spread)
    )


def test_the_digest_ignores_the_idempotency_key() -> None:
    assert digest(request_data()) == digest(request_data(idempotency_key="another-key"))


def test_defaults_digest_the_same_as_their_explicit_values() -> None:
    implicit = request_data(input={"value": {"change": "rename"}})
    del implicit["caller_metadata"]

    explicit = request_data(
        input={"value": {"change": "rename"}, "media_type": "application/json"},
        caller_metadata={},
    )

    assert digest(implicit) == digest(explicit)


def test_a_uuid_digests_the_same_in_any_case() -> None:
    assert digest(request_data(workflow_id=str(WORKFLOW_ID).upper())) == digest(request_data())


@pytest.mark.parametrize(
    "changes",
    [
        {"workflow_id": str(OTHER_WORKFLOW_ID)},
        {"input": {"value": {"change": "order-search"}}},
        {"input": {"value": "rename", "media_type": "text/plain"}},
        {"input": {"uri": "file:///Users/you/change.json", "media_type": "application/json"}},
        {"caller_metadata": {"ticket": "OPS-13"}},
        {"caller_metadata": {}},
    ],
)
def test_the_digest_changes_with_the_request(
    changes: dict[str, Any],
) -> None:
    assert digest(request_data(**changes)) != digest(request_data())


def test_a_reference_is_digested_by_its_uri_and_media_type() -> None:
    reference = request_data(
        input={"uri": "file:///Users/you/change.json", "media_type": "application/json"},
    )

    other_uri = request_data(
        input={"uri": "file:///Users/you/other.json", "media_type": "application/json"},
    )

    other_media_type = request_data(
        input={"uri": "file:///Users/you/change.json", "media_type": "text/plain"},
    )

    assert digest(reference) == digest(dict(reference))
    assert digest(reference) != digest(other_uri)
    assert digest(reference) != digest(other_media_type)


def test_non_ascii_text_digests_as_utf_8() -> None:
    request = decode_job_request(request_data(input={"value": "Grüße ✓"}))

    canonical = job_request_canonical_json(request)

    assert "Grüße ✓" in canonical
    assert job_request_digest(request) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()

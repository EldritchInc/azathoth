"""Request digests that tell a retried job from a different one (ADR 0097)."""

import hashlib
import json

from azathoth.jobs.envelope import InvokeJobRequest

DIGEST_EXCLUDED_FIELDS = frozenset({"idempotency_key"})
"""Request fields the digest leaves out: the key names the request, not its content."""


def job_request_canonical_json(
    request: InvokeJobRequest,
) -> str:
    """Return one request's canonical JSON, without its idempotency key.

    The canonical form is the request's JSON-mode dump, with defaults filled
    in, keys sorted, and no insignificant whitespace, so it is identical
    across processes, platforms, and the key order and formatting of the
    document the request came from. A reference input appears as its URI and
    media type, never as the content it names.
    """

    return json.dumps(
        request.model_dump(
            mode="json",
            exclude=set(DIGEST_EXCLUDED_FIELDS),
        ),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def job_request_digest(
    request: InvokeJobRequest,
) -> str:
    """Return the lowercase hex SHA-256 of one request's canonical JSON.

    Two requests with the same digest ask for the same invocation. Stored
    digests are compared, never recomputed: a later release whose request
    model gains fields may digest the same document differently.
    """

    return hashlib.sha256(
        job_request_canonical_json(request).encode("utf-8"),
    ).hexdigest()


__all__ = [
    "DIGEST_EXCLUDED_FIELDS",
    "job_request_canonical_json",
    "job_request_digest",
]

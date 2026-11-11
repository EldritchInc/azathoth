"""Stable content digests for durable documents."""

import hashlib
import json

from pydantic import BaseModel, JsonValue

CONTENT_DIGEST_PATTERN = r"^[0-9a-f]{64}$"


def json_digest(
    value: JsonValue,
) -> str:
    """Return the sha256 hex digest of one JSON value's canonical form.

    The canonical form has sorted keys and no insignificant whitespace, and
    is encoded as UTF-8. A document's content digest is the JSON digest of
    its dump, so a document received as JSON is checked against its content
    digest without the model that made it (ADR 0124).
    """

    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    return hashlib.sha256(
        canonical.encode("utf-8"),
    ).hexdigest()


def content_digest(
    document: BaseModel,
) -> str:
    """Return the sha256 hex digest of one document's canonical JSON.

    The canonical form is the document's JSON-mode dump with sorted keys and
    no insignificant whitespace, so the digest is identical across processes,
    platforms, and the key order or formatting of the file it was imported
    from. Two documents with the same digest describe the same content.

    The digest records content as it was when imported. A later version of
    Azathoth that adds fields to a document model may compute a different
    digest for the same file, so stored digests are compared, never
    recomputed and checked.
    """

    return json_digest(
        document.model_dump(
            mode="json",
        ),
    )

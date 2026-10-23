"""Stable content digests for durable documents."""

import hashlib
import json

from pydantic import BaseModel

CONTENT_DIGEST_PATTERN = r"^[0-9a-f]{64}$"


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

    canonical = json.dumps(
        document.model_dump(
            mode="json",
        ),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    return hashlib.sha256(
        canonical.encode("utf-8"),
    ).hexdigest()

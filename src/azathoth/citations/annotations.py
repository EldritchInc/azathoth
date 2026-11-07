"""Citation checks exported as W3C Web Annotations (ADR 0117).

Every verified check a run kept becomes one `Annotation` that highlights
the place its anchor names: its target is the anchor's source, with the
anchor's selectors as they stand, since they are already the Web Annotation
model's own (ADR 0113). The annotations of a run make one
`AnnotationCollection`, whose one page holds them all.

A source is named by the origin its content came from, with the object
version when one was recorded, or else by its digest as an RFC 6920
`ni:` URI. Every identifier is a name-based UUID of what it identifies, so
the same checks export to the same bytes.
"""

import base64
from collections.abc import Mapping, Sequence
from typing import Final, NamedTuple, cast
from urllib.parse import quote
from uuid import UUID, uuid5

from pydantic import JsonValue

from azathoth.citations.anchors import SourceAnchor
from azathoth.citations.verification import VERIFIED_STATUSES

WEB_ANNOTATION_CONTEXT: Final = "http://www.w3.org/ns/anno.jsonld"
"""The JSON-LD context of the W3C Web Annotation Data Model."""

AZATHOTH_HOMEPAGE: Final = "https://github.com/EldritchInc/azathoth"
"""The homepage an annotation's generator names."""

ANNOTATION_NAMESPACE: Final = UUID("c16d0000-0000-4000-8000-0000000000a0")
"""The namespace of the name-based UUIDs that identify exported annotations."""

CONTENT_URI_PREFIX: Final = "ni:///sha-256;"
"""The prefix of an RFC 6920 URI naming content by its SHA-256 digest."""

_VERIFIED: Final = frozenset(status.value for status in VERIFIED_STATUSES)


class CitationRecord(NamedTuple):
    """The checks one cited step of a run kept, and the record that keeps them."""

    step_id: UUID
    record: str
    checks: Sequence[Mapping[str, JsonValue]]


def content_uri(
    digest: str,
) -> str:
    """Return the RFC 6920 `ni:` URI naming content by its SHA-256 hex digest."""

    encoded = base64.urlsafe_b64encode(bytes.fromhex(digest)).decode("ascii").rstrip("=")

    return f"{CONTENT_URI_PREFIX}{encoded}"


def anchor_source(
    anchor: SourceAnchor,
) -> str:
    """Return the IRI an annotation names an anchor's content by.

    It is the origin's URI, with the S3 object version as a `versionId`
    query when the origin names one, as S3 addresses a version, or else the
    content's `ni:` URI.
    """

    if anchor.origin is None:
        return content_uri(anchor.digest)

    if anchor.origin.version_id is None:
        return anchor.origin.uri

    return f"{anchor.origin.uri}?versionId={quote(anchor.origin.version_id, safe='')}"


def citation_annotations(
    run_id: UUID,
    records: Sequence[CitationRecord],
    *,
    generator: str,
) -> dict[str, JsonValue]:
    """Return the Web Annotation collection of every verified check a run kept.

    `generator` names the software that exported them, as `Azathoth 1.3.0`.
    A check that did not verify locates nothing and is left out; the
    collection's label counts both. A collection of no annotations has no
    page.
    """

    items: list[JsonValue] = []
    left_out = 0

    for record in records:
        for index, check in enumerate(record.checks):
            anchor = check.get("anchor")

            if check.get("status") not in _VERIFIED or not isinstance(anchor, dict):
                left_out += 1
                continue

            items.append(
                _annotation(
                    run_id,
                    record,
                    index=index,
                    check=check,
                    anchor=SourceAnchor.model_validate(anchor),
                    generator=generator,
                )
            )

    label = f"Citations of run {run_id}: {len(items)} verified"

    if left_out:
        label += f", {left_out} not verified and left out"

    collection: dict[str, JsonValue] = {
        "@context": WEB_ANNOTATION_CONTEXT,
        "id": _urn(f"run:{run_id}"),
        "type": "AnnotationCollection",
        "label": f"{label}.",
        "total": len(items),
    }

    if items:
        collection["first"] = {
            "id": _urn(f"run:{run_id}:page:0"),
            "type": "AnnotationPage",
            "startIndex": 0,
            "items": items,
        }

    return collection


def _annotation(
    run_id: UUID,
    record: CitationRecord,
    *,
    index: int,
    check: Mapping[str, JsonValue],
    anchor: SourceAnchor,
    generator: str,
) -> JsonValue:
    """Return the annotation of one verified check."""

    supports = check.get("supports")
    described = f"Cited by step {record.step_id} of run {run_id}"

    if isinstance(supports, str) and supports:
        described += f", supporting {supports!r}"

    dumped = cast(dict[str, JsonValue], anchor.model_dump(mode="json", by_alias=True))

    return {
        "id": _urn(f"run:{run_id}:step:{record.step_id}:record:{record.record}:check:{index}"),
        "type": "Annotation",
        "motivation": "highlighting",
        "generator": {
            "id": AZATHOTH_HOMEPAGE,
            "type": "Software",
            "name": generator,
            "homepage": AZATHOTH_HOMEPAGE,
        },
        "body": {
            "type": "TextualBody",
            "purpose": "describing",
            "format": "text/plain",
            "value": f"{described}.",
        },
        "target": {
            "type": "SpecificResource",
            "source": anchor_source(anchor),
            "selector": dumped["selectors"],
        },
    }


def _urn(
    name: str,
) -> str:
    """Return the `urn:uuid:` IRI of a name-based UUID in the annotation namespace."""

    return f"urn:uuid:{uuid5(ANNOTATION_NAMESPACE, name)}"


__all__ = [
    "ANNOTATION_NAMESPACE",
    "AZATHOTH_HOMEPAGE",
    "CONTENT_URI_PREFIX",
    "WEB_ANNOTATION_CONTEXT",
    "CitationRecord",
    "anchor_source",
    "citation_annotations",
    "content_uri",
]

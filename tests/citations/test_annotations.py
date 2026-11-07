"""Tests that verified checks export as W3C Web Annotations (ADR 0117)."""

import hashlib
from typing import Any
from uuid import UUID, uuid5

import pytest
from pydantic import JsonValue

from azathoth.citations import (
    ANNOTATION_NAMESPACE,
    AZATHOTH_HOMEPAGE,
    CONTENT_URI_PREFIX,
    WEB_ANNOTATION_CONTEXT,
    CitationRecord,
    Segment,
    SegmentedText,
    SourceAnchor,
    anchor_source,
    citation_annotations,
    content_uri,
    verify_citation,
)
from azathoth.inputs import InputOrigin, content_bytes_digest

RUN_ID = UUID("c16e0000-0000-4000-8000-000000000001")

STEP_ID = UUID("c16e0000-0000-4000-8000-000000000002")

RECORD = "b" * 64

TEXT = "Claim 0412.\n\nReceived on December 14."

CLAIM = SegmentedText(
    tool="segment_pdf",
    version="1.0.0",
    source_digest=content_bytes_digest(b"%PDF-1.7"),
    media_type="application/pdf",
    text=TEXT,
    segments=(
        Segment(id="p1.s1", start=0, end=11, page=1),
        Segment(id="p1.s2", start=13, end=len(TEXT), page=1),
    ),
)

ORIGIN = InputOrigin(uri="s3://claims/0412.pdf", version_id="3sL4.kqtJ/lcp+XroDTDmJ")


def anchor(
    origin: InputOrigin | None = ORIGIN,
) -> SourceAnchor:
    """Return the anchor of a verified citation of the claim."""

    check = verify_citation(CLAIM, segment_id="p1.s2", quote="December 14", origin=origin)

    assert check.anchor is not None

    return check.anchor


def check(
    status: str = "verified",
    **more: JsonValue,
) -> dict[str, JsonValue]:
    """Return one kept check, anchored when it verified."""

    kept: dict[str, JsonValue] = {
        "source": "claim",
        "segment": "p1.s2",
        "quote": "December 14",
        "status": status,
        **more,
    }

    if status.startswith("verified"):
        kept["anchor"] = anchor().model_dump(mode="json", by_alias=True)

    return kept


def urn(
    name: str,
) -> str:
    """Return the name-based IRI of one exported thing."""

    return f"urn:uuid:{uuid5(ANNOTATION_NAMESPACE, name)}"


def test_content_is_named_by_its_rfc_6920_uri() -> None:
    digest = hashlib.sha256(b"Hello World!").hexdigest()

    assert content_uri(digest) == "ni:///sha-256;f4OxZX_x_FO5LcGBSKHWXfwtSx-j1ncoSt3SABJtkGk"
    assert CONTENT_URI_PREFIX == "ni:///sha-256;"


@pytest.mark.parametrize(
    ("origin", "source"),
    [
        pytest.param(None, content_uri(CLAIM.source_digest), id="no-origin"),
        pytest.param(
            InputOrigin(uri="https://claims.test/0412.pdf"),
            "https://claims.test/0412.pdf",
            id="no-version",
        ),
        pytest.param(
            ORIGIN, "s3://claims/0412.pdf?versionId=3sL4.kqtJ%2Flcp%2BXroDTDmJ", id="version"
        ),
    ],
)
def test_an_anchor_is_sourced_from_its_origin_or_its_content(
    origin: InputOrigin | None,
    source: str,
) -> None:
    assert anchor_source(anchor(origin)) == source


def test_a_verified_check_is_an_annotation_highlighting_where_its_anchor_points() -> None:
    collection = citation_annotations(
        RUN_ID,
        [CitationRecord(step_id=STEP_ID, record=RECORD, checks=[check()])],
        generator="Azathoth 1.3.0",
    )

    assert collection == {
        "@context": WEB_ANNOTATION_CONTEXT,
        "id": urn(f"run:{RUN_ID}"),
        "type": "AnnotationCollection",
        "label": f"Citations of run {RUN_ID}: 1 verified.",
        "total": 1,
        "first": {
            "id": urn(f"run:{RUN_ID}:page:0"),
            "type": "AnnotationPage",
            "startIndex": 0,
            "items": [
                {
                    "id": urn(f"run:{RUN_ID}:step:{STEP_ID}:record:{RECORD}:check:0"),
                    "type": "Annotation",
                    "motivation": "highlighting",
                    "generator": {
                        "id": AZATHOTH_HOMEPAGE,
                        "type": "Software",
                        "name": "Azathoth 1.3.0",
                        "homepage": AZATHOTH_HOMEPAGE,
                    },
                    "body": {
                        "type": "TextualBody",
                        "purpose": "describing",
                        "format": "text/plain",
                        "value": f"Cited by step {STEP_ID} of run {RUN_ID}.",
                    },
                    "target": {
                        "type": "SpecificResource",
                        "source": "s3://claims/0412.pdf?versionId=3sL4.kqtJ%2Flcp%2BXroDTDmJ",
                        "selector": anchor().model_dump(mode="json", by_alias=True)["selectors"],
                    },
                }
            ],
        },
    }


def items(
    collection: dict[str, JsonValue],
) -> list[Any]:
    """Return a collection's annotations."""

    first = collection["first"]

    assert isinstance(first, dict)
    assert isinstance(first["items"], list)

    return first["items"]


def test_a_providers_citation_names_what_it_supports() -> None:
    (annotation,) = items(
        citation_annotations(
            RUN_ID,
            [
                CitationRecord(
                    step_id=STEP_ID,
                    record=RECORD,
                    checks=[check(supports="on December 14", pages=[1, 1])],
                )
            ],
            generator="g",
        )
    )

    assert annotation["body"]["value"] == (
        f"Cited by step {STEP_ID} of run {RUN_ID}, supporting 'on December 14'."
    )


@pytest.mark.parametrize(
    "supports",
    [pytest.param("", id="empty"), pytest.param(14, id="not-text")],
)
def test_a_check_supporting_no_text_names_none(
    supports: JsonValue,
) -> None:
    (annotation,) = items(
        citation_annotations(
            RUN_ID,
            [CitationRecord(step_id=STEP_ID, record=RECORD, checks=[check(supports=supports)])],
            generator="g",
        )
    )

    assert annotation["body"]["value"] == f"Cited by step {STEP_ID} of run {RUN_ID}."


def test_unverified_checks_are_left_out_and_counted() -> None:
    collection = citation_annotations(
        RUN_ID,
        [
            CitationRecord(
                step_id=STEP_ID,
                record=RECORD,
                checks=[
                    check("quote_not_found"),
                    check(),
                    check("unknown_segment"),
                    check("verified_normalized"),
                ],
            )
        ],
        generator="g",
    )

    assert collection["label"] == (
        f"Citations of run {RUN_ID}: 2 verified, 2 not verified and left out."
    )
    assert collection["total"] == 2
    assert [annotation["id"] for annotation in items(collection)] == [
        urn(f"run:{RUN_ID}:step:{STEP_ID}:record:{RECORD}:check:1"),
        urn(f"run:{RUN_ID}:step:{STEP_ID}:record:{RECORD}:check:3"),
    ]


def test_a_verified_check_without_an_anchor_is_left_out() -> None:
    unanchored = check()
    unanchored.pop("anchor")

    collection = citation_annotations(
        RUN_ID, [CitationRecord(step_id=STEP_ID, record=RECORD, checks=[unanchored])], generator="g"
    )

    assert (collection["total"], "first" in collection) == (0, False)


def test_a_run_with_no_verified_check_has_a_collection_with_no_page() -> None:
    assert citation_annotations(RUN_ID, [], generator="g") == {
        "@context": WEB_ANNOTATION_CONTEXT,
        "id": urn(f"run:{RUN_ID}"),
        "type": "AnnotationCollection",
        "label": f"Citations of run {RUN_ID}: 0 verified.",
        "total": 0,
    }


def test_the_same_checks_export_to_the_same_collection() -> None:
    records = [
        CitationRecord(step_id=STEP_ID, record=RECORD, checks=[check(), check()]),
        CitationRecord(step_id=UUID(int=7), record="c" * 64, checks=[check()]),
    ]

    first = citation_annotations(RUN_ID, records, generator="g")

    assert citation_annotations(RUN_ID, records, generator="g") == first
    assert len({annotation["id"] for annotation in items(first)}) == 3

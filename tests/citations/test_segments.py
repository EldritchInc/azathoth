"""Tests for segments and the segmented text an extraction stores (ADR 0113)."""

import json

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.citations import (
    BoundingBox,
    Extraction,
    ExtractionError,
    Segment,
    SegmentedText,
)
from azathoth.inputs import InMemoryContentStore, content_bytes_digest

SOURCE = content_bytes_digest(b"%PDF-1.7")

TEXT = "Claim 0412.\n\nThe claim was received on December 14, 2026."


def segmented(
    *segments: Segment,
    text: str = TEXT,
    media_type: str = "text/plain",
) -> SegmentedText:
    """Return one segmented text of the test text."""

    return SegmentedText(
        tool="segment_text",
        version="1.3.0",
        source_digest=SOURCE,
        media_type=media_type,
        text=text,
        segments=segments,
    )


FIRST = Segment(id="s1", start=0, end=11)

SECOND = Segment(id="s2", start=13, end=len(TEXT))


def test_a_segment_dumps_its_span() -> None:
    assert FIRST.model_dump(mode="json") == {"id": "s1", "start": 0, "end": 11}


def test_a_segment_on_a_page_dumps_its_page_and_box() -> None:
    segment = Segment(
        id="p3.s12",
        start=40,
        end=63,
        page=3,
        bbox=BoundingBox(left=72.0, top=144.5, width=310.25, height=14.0),
    )

    assert segment.model_dump(mode="json") == {
        "id": "p3.s12",
        "start": 40,
        "end": 63,
        "page": 3,
        "bbox": {"left": 72.0, "top": 144.5, "width": 310.25, "height": 14.0},
    }


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(
            {"id": "seg-1", "start": 0, "end": 1},
            "A segment's id is s<N>, or p<PAGE>.s<N> on a page, counting from 1; got 'seg-1'.",
            id="bad-id",
        ),
        pytest.param(
            {"id": "s12x", "start": 0, "end": 1},
            "A segment's id is s<N>, or p<PAGE>.s<N> on a page, counting from 1; got 's12x'.",
            id="trailing-text",
        ),
        pytest.param(
            {"id": "s0", "start": 0, "end": 1},
            "A segment's id is s<N>, or p<PAGE>.s<N> on a page, counting from 1; got 's0'.",
            id="zero-ordinal",
        ),
        pytest.param(
            {"id": "s1", "start": 4, "end": 4},
            "Segment s1 ends after it starts; got start 4 and end 4.",
            id="empty-span",
        ),
        pytest.param(
            {"id": "s1", "start": -1, "end": 4},
            "greater than or equal to 0",
            id="negative-start",
        ),
        pytest.param(
            {"id": "p3.s1", "start": 0, "end": 1},
            "Segment p3.s1 names page 3, but has no page.",
            id="page-id-without-page",
        ),
        pytest.param(
            {"id": "s1", "start": 0, "end": 1, "page": 3},
            "Segment s1 names no page, but is on page 3.",
            id="page-without-page-id",
        ),
        pytest.param(
            {"id": "p3.s1", "start": 0, "end": 1, "page": 4},
            "Segment p3.s1 names page 3, but is on page 4.",
            id="pages-disagree",
        ),
        pytest.param(
            {
                "id": "s1",
                "start": 0,
                "end": 1,
                "bbox": {"left": 0, "top": 0, "width": 1, "height": 1},
            },
            "Segment s1 has a bounding box, which only a segment on a page has.",
            id="box-without-page",
        ),
        pytest.param(
            {"id": "p1.s1", "start": 0, "end": 1, "page": 0},
            "greater than or equal to 1",
            id="page-zero",
        ),
    ],
)
def test_a_segment_is_validated(
    fields: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        Segment.model_validate(fields)

    assert message in str(raised.value)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(
            {"left": -1, "top": 0, "width": 1, "height": 1},
            "greater than or equal to 0",
            id="negative-left",
        ),
        pytest.param(
            {"left": 0, "top": 0, "width": 0, "height": 1},
            "greater than 0",
            id="zero-width",
        ),
        pytest.param(
            {"left": 0, "top": 0, "width": 1, "height": float("inf")},
            "finite number",
            id="infinite",
        ),
        pytest.param(
            {"left": float("nan"), "top": 0, "width": 1, "height": 1},
            "finite number",
            id="not-a-number",
        ),
    ],
)
def test_a_bounding_box_is_validated(
    fields: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        BoundingBox.model_validate(fields)


def test_a_segmented_text_reads_its_segments_text() -> None:
    text = segmented(FIRST, SECOND)

    assert text.segment("s2") == SECOND
    assert text.segment("s3") is None
    assert text.segment_text(FIRST) == "Claim 0412."
    assert text.segment_text(SECOND) == "The claim was received on December 14, 2026."


def test_a_segmented_text_may_have_no_segments() -> None:
    assert segmented(text="").segments == ()


@pytest.mark.parametrize(
    ("segments", "text", "message"),
    [
        pytest.param(
            (FIRST, Segment(id="s1", start=13, end=20)),
            TEXT,
            "Segment s1 is named more than once.",
            id="duplicate-id",
        ),
        pytest.param(
            (Segment(id="s1", start=0, end=12), Segment(id="s2", start=11, end=20)),
            TEXT,
            "Segment s2 starts at 11, before segment s1 ends at 12.",
            id="overlap",
        ),
        pytest.param(
            (SECOND, FIRST),
            TEXT,
            "Segment s1 starts at 0, before segment s2 ends at 57.",
            id="out-of-order",
        ),
        pytest.param(
            (Segment(id="s1", start=0, end=len(TEXT) + 1),),
            TEXT,
            f"Segment s1 ends at {len(TEXT) + 1}, past the end of the text at {len(TEXT)}.",
            id="past-the-end",
        ),
        pytest.param(
            (),
            "Café",
            "An extraction's text is in Unicode normalization form NFC.",
            id="not-nfc",
        ),
    ],
)
def test_a_segmented_text_is_consistent(
    segments: tuple[Segment, ...],
    text: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        segmented(*segments, text=text)

    assert message in str(raised.value)


def test_a_segmented_text_stores_as_canonical_json() -> None:
    text = segmented(FIRST, SECOND)

    assert text.canonical_bytes() == json.dumps(
        text.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert text.digest() == content_bytes_digest(text.canonical_bytes())


def test_the_same_segmented_text_always_has_the_same_digest() -> None:
    assert segmented(FIRST, SECOND).digest() == segmented(FIRST, SECOND).digest()
    assert segmented(FIRST, SECOND).digest() != segmented(FIRST).digest()


def test_a_segmented_text_names_its_extraction() -> None:
    text = segmented(FIRST)

    assert text.extraction() == Extraction(
        tool="segment_text",
        version="1.3.0",
        digest=text.digest(),
    )


def test_a_stored_segmented_text_loads_back_by_its_digest() -> None:
    store = InMemoryContentStore()
    text = segmented(FIRST, SECOND)

    digest = text.store(store)

    assert digest == text.digest()
    assert SegmentedText.load(store, digest) == text


def test_loading_a_digest_the_store_lacks_finds_nothing() -> None:
    assert SegmentedText.load(InMemoryContentStore(), SOURCE) is None


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        pytest.param(b"%PDF-1.7", "it is not UTF-8 JSON", id="not-json"),
        pytest.param(b'{"text": "x"}', "Field required", id="not-a-segmented-text"),
    ],
)
def test_loading_other_content_says_why_it_is_not_a_segmented_text(
    content: bytes,
    reason: str,
) -> None:
    store = InMemoryContentStore()
    digest = store.put(content)

    with pytest.raises(ExtractionError) as raised:
        SegmentedText.load(store, digest)

    assert str(raised.value).startswith(f"Content {digest} is not a segmented text: ")
    assert reason in str(raised.value)


def test_a_segment_with_a_box_round_trips_through_the_store() -> None:
    store = InMemoryContentStore()
    page = segmented(
        Segment(
            id="p1.s1",
            start=0,
            end=11,
            page=1,
            bbox=BoundingBox(left=72.0, top=72.0, width=0.1, height=14.0),
        ),
        media_type="application/pdf",
    )

    assert SegmentedText.load(store, page.store(store)) == page

"""Tests for the pages an extraction lists of its source (ADR 0114)."""

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.citations import BoundingBox, Segment, SegmentedText, SourcePage
from azathoth.inputs import PDF_MEDIA_TYPE, InMemoryContentStore, content_bytes_digest

SOURCE = content_bytes_digest(b"%PDF-1.7")

TEXT = "Claim 0412.\n\nApproved."

FIRST = Segment(id="p1.s1", start=0, end=11, page=1)

THIRD = Segment(id="p3.s1", start=13, end=len(TEXT), page=3)

PAGES = (
    SourcePage(page=1, width=612.0, height=792.0, has_text=True),
    SourcePage(page=2, width=612.0, height=792.0, has_text=False),
    SourcePage(page=3, width=792.0, height=612.0, has_text=True),
)


def segmented(
    segments: tuple[Segment, ...] = (FIRST, THIRD),
    pages: tuple[SourcePage, ...] = PAGES,
) -> SegmentedText:
    """Return one segmented text of a three-page PDF."""

    return SegmentedText(
        tool="segment_pdf",
        version="1.0.0",
        source_digest=SOURCE,
        media_type=PDF_MEDIA_TYPE,
        text=TEXT,
        segments=segments,
        pages=pages,
    )


def test_an_extraction_lists_its_pages_in_its_dump() -> None:
    dumped = segmented().model_dump(mode="json")

    assert dumped["pages"] == [
        {"page": 1, "width": 612.0, "height": 792.0, "has_text": True},
        {"page": 2, "width": 612.0, "height": 792.0, "has_text": False},
        {"page": 3, "width": 792.0, "height": 612.0, "has_text": True},
    ]


def test_an_extraction_that_lists_no_pages_leaves_them_out_of_its_dump() -> None:
    plain = SegmentedText(
        tool="segment_text",
        version="1",
        source_digest=SOURCE,
        media_type="text/plain",
        text=TEXT,
        segments=(Segment(id="s1", start=0, end=11),),
    )

    assert "pages" not in plain.model_dump(mode="json")
    assert b'"pages"' not in plain.canonical_bytes()


def test_listing_pages_changes_the_digest() -> None:
    assert segmented().digest() != segmented(pages=()).digest()


def test_listed_pages_round_trip_through_the_store() -> None:
    store = InMemoryContentStore()
    text = segmented()

    assert SegmentedText.load(store, text.store(store)) == text


def test_a_listed_page_is_found_by_its_number() -> None:
    text = segmented()

    assert text.page(2) == PAGES[1]
    assert [text.page(number) for number in (0, 4)] == [None, None]
    assert segmented(pages=()).page(1) is None


@pytest.mark.parametrize(
    ("value", "message"),
    [
        pytest.param(
            {"page": 0, "width": 612, "height": 792, "has_text": True},
            "greater than or equal to 1",
            id="page-zero",
        ),
        pytest.param(
            {"page": 1, "width": 0, "height": 792, "has_text": True},
            "greater than 0",
            id="no-width",
        ),
        pytest.param(
            {"page": 1, "width": 612, "height": float("inf"), "has_text": True},
            "finite number",
            id="infinite-height",
        ),
        pytest.param(
            {"page": 1, "width": 612, "height": 792, "has_text": 1},
            "valid boolean",
            id="has-text-not-a-boolean",
        ),
        pytest.param(
            {"page": 1, "width": 612, "height": 792, "has_text": True, "rotate": 90},
            "Extra inputs are not permitted",
            id="extra-field",
        ),
    ],
)
def test_a_source_page_is_validated(
    value: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        SourcePage.model_validate(value)

    assert message in str(raised.value)


@pytest.mark.parametrize(
    ("segments", "pages", "message"),
    [
        pytest.param(
            (FIRST, THIRD),
            (PAGES[0], PAGES[2], PAGES[1]),
            "Page 3 is listed as page 2; pages are listed in order, from 1.",
            id="out-of-order",
        ),
        pytest.param(
            (FIRST,),
            (PAGES[1],),
            "Page 2 is listed as page 1; pages are listed in order, from 1.",
            id="not-from-1",
        ),
        pytest.param(
            (FIRST, THIRD),
            PAGES[:2],
            "Segment p3.s1 is on page 3, but the extraction lists 2 pages.",
            id="segment-past-the-pages",
        ),
        pytest.param(
            (Segment(id="s1", start=0, end=11),),
            PAGES,
            "Segment s1 names no page, but the extraction lists its pages.",
            id="segment-on-no-page",
        ),
        pytest.param(
            (FIRST,),
            PAGES,
            "Page 3 has text, but no segment is on it.",
            id="text-without-segments",
        ),
        pytest.param(
            (FIRST, Segment(id="p2.s1", start=13, end=len(TEXT), page=2)),
            (PAGES[0], PAGES[1]),
            "Page 2 has no text, but segment p2.s1 is on it.",
            id="segments-without-text",
        ),
    ],
)
def test_listed_pages_agree_with_the_segments(
    segments: tuple[Segment, ...],
    pages: tuple[SourcePage, ...],
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        segmented(segments, pages)

    assert message in str(raised.value)


def test_a_page_with_several_segments_names_the_first_when_it_has_no_text() -> None:
    with pytest.raises(ValidationError) as raised:
        segmented(
            (
                Segment(id="p1.s1", start=0, end=5, page=1),
                Segment(id="p1.s2", start=6, end=11, page=1),
            ),
            (SourcePage(page=1, width=612.0, height=792.0, has_text=False),),
        )

    assert "Page 1 has no text, but segment p1.s1 is on it." in str(raised.value)


def test_a_segment_box_is_kept_beside_its_listed_page() -> None:
    box = BoundingBox(left=72.0, top=82.48, width=50.0, height=12.0)
    text = segmented(
        (Segment(id="p1.s1", start=0, end=11, page=1, bbox=box), THIRD),
    )

    assert text.segments[0].bbox == box
    assert text.page(1) == PAGES[0]

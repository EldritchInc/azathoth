"""Tests for checking a citation against the segment it names (ADR 0113)."""

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.citations import (
    PDF_FRAGMENT_SPECIFICATION,
    QUOTE_CONTEXT_LENGTH,
    BoundingBox,
    CitationCheck,
    CitationStatus,
    FragmentSelector,
    Segment,
    SegmentedText,
    SourceAnchor,
    TextPositionSelector,
    TextQuoteSelector,
    verify_citation,
)
from azathoth.inputs import InputOrigin, content_bytes_digest

SOURCE = content_bytes_digest(b"claim 0412")

ORIGIN = InputOrigin(uri="s3://claims-intake/2026/11/claim-0412.txt", etag="9b2c")

PARAGRAPHS = (
    "Claim 0412.",
    "The claim was\nreceived on December 14, 2026.",
    "\u201cLate,\u201d the adjuster wrote \u2014 twice.",
    "Caf\u00e9 receipts: received, received, received.",
)

TEXT = "\n\n".join(PARAGRAPHS)


def segments() -> tuple[Segment, ...]:
    """Return one segment per paragraph of the test text."""

    found: list[Segment] = []
    start = 0

    for number, paragraph in enumerate(PARAGRAPHS, start=1):
        start = TEXT.index(paragraph, start)
        found.append(Segment(id=f"s{number}", start=start, end=start + len(paragraph)))
        start += len(paragraph)

    return tuple(found)


SEGMENTED = SegmentedText(
    tool="segment_text",
    version="1.3.0",
    source_digest=SOURCE,
    media_type="text/plain",
    text=TEXT,
    segments=segments(),
)


def check(
    segment_id: str,
    quote: str,
    *,
    segmented: SegmentedText = SEGMENTED,
    origin: InputOrigin | None = ORIGIN,
) -> CitationCheck:
    """Check one citation of the test text."""

    return verify_citation(segmented, segment_id=segment_id, quote=quote, origin=origin)


def expected_anchor(
    start: int,
    end: int,
    *,
    segmented: SegmentedText = SEGMENTED,
    origin: InputOrigin | None = ORIGIN,
    fragment: FragmentSelector | None = None,
) -> SourceAnchor:
    """Return the anchor a verified citation of one span of the text should hold."""

    text = segmented.text

    return SourceAnchor(
        digest=segmented.source_digest,
        media_type=segmented.media_type,
        origin=origin,
        selectors=(
            TextQuoteSelector(
                exact=text[start:end],
                prefix=text[max(0, start - QUOTE_CONTEXT_LENGTH) : start],
                suffix=text[end : end + QUOTE_CONTEXT_LENGTH],
            ),
            TextPositionSelector(start=start, end=end),
            *((fragment,) if fragment is not None else ()),
        ),
        extraction=segmented.extraction(),
    )


def test_the_statuses_are_the_four_agreed() -> None:
    assert [status.value for status in CitationStatus] == [
        "verified",
        "verified_normalized",
        "quote_not_found",
        "unknown_segment",
    ]


def test_the_context_around_a_quote_is_32_code_points() -> None:
    assert QUOTE_CONTEXT_LENGTH == 32


def test_an_exact_quote_in_its_segment_is_verified() -> None:
    start = TEXT.index("received on December 14")
    end = start + len("received on December 14")

    assert check("s2", "received on December 14") == CitationCheck(
        status=CitationStatus.VERIFIED,
        segment_id="s2",
        quote="received on December 14",
        occurrences=1,
        anchor=expected_anchor(start, end),
    )


def test_the_context_runs_past_the_segment_into_the_text_around_it() -> None:
    result = check("s2", "The claim")

    assert result.anchor is not None

    quote = result.anchor.selectors[0]

    assert isinstance(quote, TextQuoteSelector)
    assert quote.prefix == "Claim 0412.\n\n"
    assert quote.suffix == TEXT[TEXT.index("The claim") + 9 :][:32]


def test_a_quote_at_the_start_of_the_text_has_an_empty_prefix() -> None:
    result = check("s1", "Claim")

    assert result.anchor == expected_anchor(0, 5)
    assert result.anchor is not None
    assert result.anchor.selectors[0] == TextQuoteSelector(
        exact="Claim",
        prefix="",
        suffix=TEXT[5:37],
    )


def test_a_quote_at_the_end_of_the_text_has_a_short_suffix() -> None:
    result = check("s4", "received.")

    end = len(TEXT)

    assert result.anchor == expected_anchor(end - 9, end)


def test_a_quote_from_another_segment_is_not_found_in_the_one_cited() -> None:
    assert check("s1", "received on December 14") == CitationCheck(
        status=CitationStatus.QUOTE_NOT_FOUND,
        segment_id="s1",
        quote="received on December 14",
    )


def test_a_quote_spanning_two_segments_is_not_found() -> None:
    assert check("s1", "0412.\n\nThe claim").status is CitationStatus.QUOTE_NOT_FOUND


def test_a_segment_the_extraction_lacks_is_unknown() -> None:
    assert check("s9", "Claim") == CitationCheck(
        status=CitationStatus.UNKNOWN_SEGMENT,
        segment_id="s9",
        quote="Claim",
    )


def test_a_page_segment_named_without_its_page_is_unknown() -> None:
    assert check("p1.s1", "Claim").status is CitationStatus.UNKNOWN_SEGMENT


@pytest.mark.parametrize("quote", ["", " ", "\n\t"])
def test_an_empty_quote_is_never_found(
    quote: str,
) -> None:
    assert check("s1", quote).status is CitationStatus.QUOTE_NOT_FOUND


def test_matching_is_case_sensitive() -> None:
    assert check("s2", "RECEIVED on December 14").status is CitationStatus.QUOTE_NOT_FOUND


def test_a_quote_with_straightened_punctuation_is_verified_normalized() -> None:
    result = check("s3", '"Late," the adjuster wrote - twice.')

    start = TEXT.index("\u201cLate")
    end = start + len(PARAGRAPHS[2])

    assert result == CitationCheck(
        status=CitationStatus.VERIFIED_NORMALIZED,
        segment_id="s3",
        quote='"Late," the adjuster wrote - twice.',
        occurrences=1,
        anchor=expected_anchor(start, end),
    )


def test_a_normalized_match_anchors_the_sources_own_text() -> None:
    result = check("s2", "The claim was received on   December 14")

    assert result.status is CitationStatus.VERIFIED_NORMALIZED
    assert result.anchor is not None
    assert result.anchor.selectors[0] == TextQuoteSelector(
        exact="The claim was\nreceived on December 14",
        prefix="Claim 0412.\n\n",
        suffix=", 2026.\n\n\u201cLate,\u201d the adjuster wr",
    )


def test_surrounding_whitespace_in_a_quote_is_ignored() -> None:
    result = check("s2", "  received on December 14\n")

    assert result.status is CitationStatus.VERIFIED_NORMALIZED
    assert result.anchor is not None
    assert result.anchor.selectors[0] == TextQuoteSelector(
        exact="received on December 14",
        prefix="Claim 0412.\n\nThe claim was\n",
        suffix=TEXT[TEXT.index(", 2026") :][:32],
    )


def test_a_decomposed_quote_matches_composed_text() -> None:
    result = check("s4", "Cafe\u0301 receipts")

    assert result.status is CitationStatus.VERIFIED_NORMALIZED
    assert result.anchor is not None
    assert isinstance(result.anchor.selectors[0], TextQuoteSelector)
    assert result.anchor.selectors[0].exact == "Caf\u00e9 receipts"


def test_a_non_breaking_space_counts_as_whitespace() -> None:
    assert check("s2", "received\u00a0on December 14").status is (
        CitationStatus.VERIFIED_NORMALIZED
    )


@pytest.mark.parametrize(
    ("character", "plain"),
    [
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201a", "'"),
        ("\u201b", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u201e", '"'),
        ("\u201f", '"'),
        ("\u2010", "-"),
        ("\u2011", "-"),
        ("\u2012", "-"),
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("\u2015", "-"),
        ("\u2212", "-"),
    ],
)
def test_each_curly_quote_and_dash_matches_its_plain_form(
    character: str,
    plain: str,
) -> None:
    text = f"The word {character}here{character}."
    segmented = SegmentedText(
        tool="segment_text",
        version="1.3.0",
        source_digest=SOURCE,
        media_type="text/plain",
        text=text,
        segments=(Segment(id="s1", start=0, end=len(text)),),
    )

    result = check("s1", f"{plain}here{plain}", segmented=segmented, origin=None)

    assert result.status is CitationStatus.VERIFIED_NORMALIZED
    assert result.anchor is not None
    assert isinstance(result.anchor.selectors[0], TextQuoteSelector)
    assert result.anchor.selectors[0].exact == f"{character}here{character}"


def test_a_quote_found_more_than_once_anchors_the_first_and_counts_them() -> None:
    result = check("s4", "received")

    start = TEXT.index("received,")

    assert result.occurrences == 3
    assert result.anchor == expected_anchor(start, start + len("received"))


def test_overlapping_occurrences_are_each_counted() -> None:
    text = "aaaa"
    segmented = SegmentedText(
        tool="segment_text",
        version="1.3.0",
        source_digest=SOURCE,
        media_type="text/plain",
        text=text,
        segments=(Segment(id="s1", start=0, end=4),),
    )

    assert check("s1", "aa", segmented=segmented).occurrences == 3


def test_normalized_occurrences_are_counted_in_the_normalized_segment() -> None:
    result = check("s4", "received,  received")

    assert result.status is CitationStatus.VERIFIED_NORMALIZED
    assert result.occurrences == 2


def test_an_anchor_without_an_origin_leaves_it_out() -> None:
    result = check("s1", "Claim", origin=None)

    assert result.anchor is not None
    assert result.anchor.origin is None


def pdf(
    segment: Segment,
) -> SegmentedText:
    """Return a segmented PDF text holding one segment over the whole text."""

    return SegmentedText(
        tool="segment_pdf",
        version="1.3.0",
        source_digest=SOURCE,
        media_type="application/pdf",
        text="Received on December 14.",
        segments=(segment,),
    )


def test_a_pdf_segment_on_a_page_locates_its_page() -> None:
    segmented = pdf(Segment(id="p3.s1", start=0, end=24, page=3))

    result = check("p3.s1", "December 14", segmented=segmented)

    assert result.anchor == expected_anchor(
        12,
        23,
        segmented=segmented,
        fragment=FragmentSelector(value="page=3", conformsTo=PDF_FRAGMENT_SPECIFICATION),
    )


def test_a_pdf_segment_with_a_box_locates_its_rectangle_on_the_page() -> None:
    segmented = pdf(
        Segment(
            id="p3.s1",
            start=0,
            end=24,
            page=3,
            bbox=BoundingBox(left=72.0, top=144.5, width=310.25, height=14.0),
        )
    )

    result = check("p3.s1", "December 14", segmented=segmented)

    assert result.anchor is not None
    assert result.anchor.selectors[2] == FragmentSelector(
        value="page=3&viewrect=72,144.5,310.25,14",
        conformsTo=PDF_FRAGMENT_SPECIFICATION,
    )


def test_a_viewrect_rounds_to_hundredths_of_a_point() -> None:
    segmented = pdf(
        Segment(
            id="p1.s1",
            start=0,
            end=24,
            page=1,
            bbox=BoundingBox(left=0.004, top=1000.0, width=12.3456, height=0.5),
        )
    )

    result = check("p1.s1", "December", segmented=segmented)

    assert result.anchor is not None
    assert result.anchor.selectors[2] == FragmentSelector(
        value="page=1&viewrect=0,1000,12.35,0.5",
        conformsTo=PDF_FRAGMENT_SPECIFICATION,
    )


def test_a_check_dumps_its_status_citation_and_anchor() -> None:
    dumped = check("s1", "Claim").model_dump(mode="json")

    assert list(dumped) == ["status", "segment_id", "quote", "occurrences", "anchor"]
    assert dumped["status"] == "verified"


def test_a_failed_check_leaves_out_its_anchor() -> None:
    assert check("s9", "Claim").model_dump(mode="json") == {
        "status": "unknown_segment",
        "segment_id": "s9",
        "quote": "Claim",
        "occurrences": 0,
    }


def test_a_check_reads_back_from_its_dump() -> None:
    result = check("s3", '"Late," the adjuster')

    assert CitationCheck.model_validate(result.model_dump(mode="json")) == result


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(
            {"status": "verified", "occurrences": 1},
            "A citation check with status verified holds the anchor it verified.",
            id="verified-without-anchor",
        ),
        pytest.param(
            {"status": "verified_normalized", "occurrences": 1},
            "A citation check with status verified_normalized holds the anchor it verified.",
            id="normalized-without-anchor",
        ),
        pytest.param(
            {"status": "quote_not_found", "anchor": "ANCHOR"},
            "A citation check with status quote_not_found holds no anchor.",
            id="failure-with-anchor",
        ),
        pytest.param(
            {"status": "verified", "occurrences": 0, "anchor": "ANCHOR"},
            "A citation check with status verified found its quote at least once.",
            id="verified-without-occurrences",
        ),
        pytest.param(
            {"status": "unknown_segment", "occurrences": 2},
            "A citation check with status unknown_segment found no occurrences.",
            id="failure-with-occurrences",
        ),
    ],
)
def test_a_check_is_consistent(
    fields: dict[str, JsonValue],
    message: str,
) -> None:
    anchor = check("s1", "Claim").anchor

    assert anchor is not None

    data: dict[str, JsonValue] = {"segment_id": "s1", "quote": "Claim", **fields}

    if data.get("anchor") == "ANCHOR":
        data["anchor"] = anchor.model_dump(mode="json")

    with pytest.raises(ValidationError) as raised:
        CitationCheck.model_validate(data)

    assert message in str(raised.value)


def test_a_run_of_whitespace_in_the_source_matches_one_space() -> None:
    text = "Received   on\n\n\tDecember 14."
    segmented = SegmentedText(
        tool="segment_text",
        version="1.3.0",
        source_digest=SOURCE,
        media_type="text/plain",
        text=text,
        segments=(Segment(id="s1", start=0, end=len(text)),),
    )

    result = check("s1", "Received on December 14", segmented=segmented, origin=None)

    assert result.status is CitationStatus.VERIFIED_NORMALIZED
    assert result.anchor is not None
    assert isinstance(result.anchor.selectors[0], TextQuoteSelector)
    assert result.anchor.selectors[0].exact == "Received   on\n\n\tDecember 14"


def test_a_page_segment_of_other_content_has_no_page_fragment() -> None:
    text = "Received on December 14."
    segmented = SegmentedText(
        tool="segment_pages",
        version="1.3.0",
        source_digest=SOURCE,
        media_type="text/plain",
        text=text,
        segments=(Segment(id="p2.s1", start=0, end=len(text), page=2),),
    )

    result = check("p2.s1", "December 14", segmented=segmented, origin=None)

    assert result.anchor is not None
    assert [type(selector) for selector in result.anchor.selectors] == [
        TextQuoteSelector,
        TextPositionSelector,
    ]

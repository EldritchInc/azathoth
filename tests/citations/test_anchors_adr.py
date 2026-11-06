"""Tests that ADR 0113 states source anchors as they really behave."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.citations import (
    FRAGMENT_SPECIFICATIONS,
    PDF_FRAGMENT_SPECIFICATION,
    PLAIN_PUNCTUATION,
    QUOTE_CONTEXT_LENGTH,
    BoundingBox,
    CitationCheck,
    CitationStatus,
    Extraction,
    FragmentSelector,
    Segment,
    SegmentedText,
    SourceAnchor,
    TextPositionSelector,
    TextQuoteSelector,
    verify_citation,
)
from azathoth.inputs import content_bytes_digest

ADR = Path(__file__).parents[2] / "docs" / "adrs" / "0113-anchor-and-verify-citations.md"

DIGEST = content_bytes_digest(b"%PDF-1.7")


def text() -> str:
    """Return the ADR."""

    return ADR.read_text(encoding="utf-8")


def prose() -> str:
    """Return the ADR with its lines joined, as it reads."""

    return " ".join(text().split())


def assert_quoted(
    message: str,
) -> None:
    """Check the ADR quotes one message as a whole `text` block."""

    assert f"```text\n{message}\n```" in text(), message


def validation_message(
    error: ValidationError,
) -> str:
    """Return one validation error's single message, without pydantic's prefix."""

    (detail,) = error.errors(include_url=False)

    return str(detail["msg"]).removeprefix("Value error, ")


def test_the_adr_names_every_fragment_specification() -> None:
    for specification in FRAGMENT_SPECIFICATIONS:
        assert f"`{specification}`" in text(), specification


def test_the_adr_names_every_selector_type() -> None:
    for name in ("TextQuoteSelector", "TextPositionSelector", "FragmentSelector"):
        assert f"`{name}`" in text(), name


def test_the_adr_says_positions_count_code_points() -> None:
    assert "Unicode code points" in prose()
    assert "`start` is included and `end` is not" in prose()


def test_the_adr_quotes_the_refusal_of_a_fragment_that_cannot_locate_its_content() -> None:
    with pytest.raises(ValidationError) as raised:
        SourceAnchor(
            digest=DIGEST,
            media_type="image/png",
            selectors=(FragmentSelector(value="page=3", conformsTo=PDF_FRAGMENT_SPECIFICATION),),
        )

    assert_quoted(validation_message(raised.value))


def test_the_adr_quotes_the_refusal_of_text_selectors_without_an_extraction() -> None:
    with pytest.raises(ValidationError) as raised:
        SourceAnchor(
            digest=DIGEST,
            media_type="application/pdf",
            selectors=(TextQuoteSelector(exact="received"),),
        )

    assert_quoted(validation_message(raised.value))


def test_the_adr_quotes_the_refusal_of_a_quote_and_position_that_disagree() -> None:
    with pytest.raises(ValidationError) as raised:
        SourceAnchor(
            digest=DIGEST,
            media_type="application/pdf",
            selectors=(
                TextQuoteSelector(exact="received on December 14"),
                TextPositionSelector(start=0, end=5),
            ),
            extraction=Extraction(tool="segment_pdf", version="1.3.0", digest=DIGEST),
        )

    assert_quoted(validation_message(raised.value))


def test_the_adr_quotes_the_refusal_of_text_not_in_nfc() -> None:
    with pytest.raises(ValidationError) as raised:
        SegmentedText(
            tool="segment_text",
            version="1.3.0",
            source_digest=DIGEST,
            media_type="text/plain",
            text="Cafe\u0301",
        )

    assert_quoted(validation_message(raised.value))


def test_the_adr_shows_a_valid_segment() -> None:
    assert Segment.model_validate(
        {
            "id": "p3.s12",
            "start": 18234,
            "end": 18311,
            "page": 3,
            "bbox": {"left": 72.0, "top": 144.5, "width": 310.25, "height": 14.0},
        }
    )
    assert '"id": "p3.s12"' in text()


def test_the_adr_says_how_segment_ids_read_and_boxes_measure() -> None:
    assert "`s<N>`, or `p<PAGE>.s<N>` for a segment on a page" in prose()
    assert "in points from the page's top-left corner" in prose()


def test_the_adr_says_extractions_store_as_canonical_json() -> None:
    assert "canonical JSON, with sorted keys and no insignificant whitespace" in prose()


def test_the_adr_names_every_status() -> None:
    for status in CitationStatus:
        assert f"- `{status.value}`:" in text(), status


def test_the_adr_states_the_context_length() -> None:
    assert QUOTE_CONTEXT_LENGTH == 32
    assert "up to 32 Unicode code points before and after it" in prose()


def test_the_adr_states_the_normalization() -> None:
    assert set(PLAIN_PUNCTUATION.values()) == {"'", '"', "-"}
    assert "curly quotes as plain `'` and `\"`, and dashes and the minus sign as `-`" in prose()
    assert "Matching stays case-sensitive" in prose()


def test_the_adr_shows_the_viewrect_a_check_builds() -> None:
    segmented = SegmentedText(
        tool="segment_pdf",
        version="1.3.0",
        source_digest=DIGEST,
        media_type="application/pdf",
        text="Received on December 14.",
        segments=(
            Segment(
                id="p3.s12",
                start=0,
                end=24,
                page=3,
                bbox=BoundingBox(left=72.0, top=144.5, width=310.25, height=14.0),
            ),
        ),
    )

    anchor = verify_citation(segmented, segment_id="p3.s12", quote="December").anchor

    assert anchor is not None

    fragment = anchor.selectors[2]

    assert isinstance(fragment, FragmentSelector)
    assert fragment.model_dump_json().replace('":"', '": "').replace('","', '", "') in text()


def test_the_adr_shows_a_check_as_it_is_recorded() -> None:
    assert list(CitationCheck.model_fields) == [
        "status",
        "segment_id",
        "quote",
        "occurrences",
        "anchor",
    ]
    assert '"status": "verified_normalized"' in text()

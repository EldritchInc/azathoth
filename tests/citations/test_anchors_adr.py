"""Tests that ADR 0113 states source anchors as they really behave."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.citations import (
    FRAGMENT_SPECIFICATIONS,
    PDF_FRAGMENT_SPECIFICATION,
    Extraction,
    FragmentSelector,
    Segment,
    SegmentedText,
    SourceAnchor,
    TextPositionSelector,
    TextQuoteSelector,
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

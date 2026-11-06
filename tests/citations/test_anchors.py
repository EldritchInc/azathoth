"""Tests for source anchors: where in exactly which content something is (ADR 0113)."""

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.citations import (
    MEDIA_FRAGMENT_SPECIFICATION,
    PDF_FRAGMENT_SPECIFICATION,
    Extraction,
    FragmentSelector,
    SourceAnchor,
    TextPositionSelector,
    TextQuoteSelector,
)
from azathoth.inputs import InputOrigin, content_bytes_digest

DIGEST = content_bytes_digest(b"%PDF-1.7")

EXTRACTION = Extraction(
    tool="segment_pdf",
    version="1.3.0",
    digest=content_bytes_digest(b'{"segments":[]}'),
)

ORIGIN = InputOrigin(
    uri="s3://claims-intake/2026/11/claim-0412.pdf",
    version_id="3HL4kqtJlcpXroDTDmJ",
)

QUOTE = TextQuoteSelector(exact="received on December 14", prefix="was ", suffix=", 2026")

POSITION = TextPositionSelector(start=18234, end=18257)

PAGE = FragmentSelector(value="page=3", conformsTo=PDF_FRAGMENT_SPECIFICATION)


def anchor(
    *selectors: TextQuoteSelector | TextPositionSelector | FragmentSelector,
    media_type: str = "application/pdf",
    origin: InputOrigin | None = ORIGIN,
    extraction: Extraction | None = EXTRACTION,
) -> SourceAnchor:
    """Return an anchor of the test PDF with some selectors."""

    return SourceAnchor(
        digest=DIGEST,
        media_type=media_type,
        origin=origin,
        selectors=selectors,
        extraction=extraction,
    )


def test_an_extraction_names_its_tool_version_and_output() -> None:
    assert EXTRACTION.model_dump(mode="json") == {
        "tool": "segment_pdf",
        "version": "1.3.0",
        "digest": content_bytes_digest(b'{"segments":[]}'),
    }


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param({"tool": "", "version": "1", "digest": DIGEST}, "at least 1", id="no-tool"),
        pytest.param({"tool": "t", "version": "", "digest": DIGEST}, "at least 1", id="no-version"),
        pytest.param({"tool": "t", "version": "1", "digest": "abc"}, "pattern", id="bad-digest"),
    ],
)
def test_an_extraction_is_validated(
    fields: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Extraction.model_validate(fields)


def test_an_anchor_dumps_every_part_with_w3c_selectors() -> None:
    assert anchor(QUOTE, POSITION, PAGE).model_dump(mode="json") == {
        "digest": DIGEST,
        "media_type": "application/pdf",
        "origin": {
            "uri": "s3://claims-intake/2026/11/claim-0412.pdf",
            "version_id": "3HL4kqtJlcpXroDTDmJ",
        },
        "selectors": [
            {
                "type": "TextQuoteSelector",
                "exact": "received on December 14",
                "prefix": "was ",
                "suffix": ", 2026",
            },
            {"type": "TextPositionSelector", "start": 18234, "end": 18257},
            {
                "type": "FragmentSelector",
                "value": "page=3",
                "conformsTo": "http://tools.ietf.org/rfc/rfc3778",
            },
        ],
        "extraction": EXTRACTION.model_dump(mode="json"),
    }


def test_an_anchor_leaves_out_an_origin_and_extraction_it_lacks() -> None:
    dumped = anchor(PAGE, origin=None, extraction=None).model_dump(mode="json")

    assert set(dumped) == {"digest", "media_type", "selectors"}


def test_an_anchor_reads_back_from_its_dump() -> None:
    original = anchor(QUOTE, POSITION, PAGE)

    assert SourceAnchor.model_validate(original.model_dump(mode="json")) == original


def test_an_image_anchor_locates_a_region_by_media_fragment() -> None:
    region = FragmentSelector(value="xywh=160,120,320,240", conformsTo=MEDIA_FRAGMENT_SPECIFICATION)

    assert anchor(region, media_type="image/png", extraction=None).selectors == (region,)


@pytest.mark.parametrize(
    ("selectors", "media_type", "extraction", "message"),
    [
        pytest.param(
            (),
            "application/pdf",
            EXTRACTION,
            "A source anchor holds at least one selector.",
            id="no-selectors",
        ),
        pytest.param(
            (QUOTE, TextQuoteSelector(exact="December")),
            "application/pdf",
            EXTRACTION,
            "A source anchor holds at most one TextQuoteSelector.",
            id="two-quotes",
        ),
        pytest.param(
            (POSITION, TextPositionSelector(start=1, end=2)),
            "application/pdf",
            EXTRACTION,
            "A source anchor holds at most one TextPositionSelector.",
            id="two-positions",
        ),
        pytest.param(
            (PAGE, FragmentSelector(value="page=4", conformsTo=PDF_FRAGMENT_SPECIFICATION)),
            "application/pdf",
            EXTRACTION,
            "A source anchor holds at most one FragmentSelector.",
            id="two-fragments",
        ),
        pytest.param(
            (QUOTE, TextPositionSelector(start=0, end=5)),
            "application/pdf",
            EXTRACTION,
            "A source anchor's quote is 23 characters long, but its position spans 5.",
            id="quote-and-position-disagree",
        ),
        pytest.param(
            (QUOTE,),
            "application/pdf",
            None,
            "A source anchor's text selectors count the text of an extraction, "
            "so the anchor names its extraction.",
            id="quote-without-extraction",
        ),
        pytest.param(
            (POSITION,),
            "text/plain",
            None,
            "A source anchor's text selectors count the text of an extraction, "
            "so the anchor names its extraction.",
            id="position-without-extraction",
        ),
        pytest.param(
            (PAGE,),
            "image/png",
            None,
            "A FragmentSelector conforming to http://tools.ietf.org/rfc/rfc3778 "
            "cannot locate image/png content.",
            id="pdf-fragment-on-an-image",
        ),
        pytest.param(
            (FragmentSelector(value="xywh=0,0,10,10", conformsTo=MEDIA_FRAGMENT_SPECIFICATION),),
            "application/pdf",
            None,
            "A FragmentSelector conforming to http://www.w3.org/TR/media-frags/ "
            "cannot locate application/pdf content.",
            id="media-fragment-on-a-pdf",
        ),
        pytest.param(
            (FragmentSelector(value="page=1", conformsTo=PDF_FRAGMENT_SPECIFICATION),),
            "text/plain",
            None,
            "A FragmentSelector conforming to http://tools.ietf.org/rfc/rfc3778 "
            "cannot locate text/plain content.",
            id="pdf-fragment-on-text",
        ),
    ],
)
def test_an_anchor_is_consistent(
    selectors: tuple[TextQuoteSelector | TextPositionSelector | FragmentSelector, ...],
    media_type: str,
    extraction: Extraction | None,
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        anchor(*selectors, media_type=media_type, extraction=extraction)

    assert message in str(raised.value)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param({"digest": "ABC"}, "pattern", id="bad-digest"),
        pytest.param({"media_type": "image/gif"}, "is not supported", id="unsupported-type"),
        pytest.param({"page": 3}, "Extra inputs are not permitted", id="extra-field"),
    ],
)
def test_an_anchors_fields_are_validated(
    fields: dict[str, JsonValue],
    message: str,
) -> None:
    data = anchor(PAGE, extraction=None).model_dump(mode="json")
    data.update(fields)

    with pytest.raises(ValidationError, match=message):
        SourceAnchor.model_validate(data)


def test_a_quote_counts_code_points_not_utf16_units() -> None:
    #
    # "café 🙂" is six code points: the emoji is one, though UTF-16 needs two.
    #
    quote = TextQuoteSelector(exact="café 🙂")

    assert anchor(quote, TextPositionSelector(start=10, end=16), media_type="text/plain")


def test_an_anchor_is_frozen() -> None:
    with pytest.raises(ValidationError, match="Instance is frozen"):
        anchor(PAGE).__setattr__("digest", DIGEST)

"""Checking a citation against the segment it names (ADR 0113).

A citation names a segment of an extraction and quotes it. Azathoth looks for
the quote in that segment only, never elsewhere in the document, so a
citation cannot borrow a quote from a page it does not name. A quote found
exactly is `verified`. One found only after a documented normalization is
`verified_normalized`. Either way the anchor holds the source's own text,
never the quote as cited.
"""

import unicodedata
from enum import StrEnum
from typing import Final, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from azathoth.citations.anchors import SourceAnchor
from azathoth.citations.segments import BoundingBox, Segment, SegmentedText
from azathoth.citations.selectors import (
    PDF_FRAGMENT_SPECIFICATION,
    FragmentSelector,
    TextPositionSelector,
    TextQuoteSelector,
)
from azathoth.inputs import PDF_MEDIA_TYPE, InputOrigin

QUOTE_CONTEXT_LENGTH: Final = 32
"""How many code points of text before and after a quote its selector holds."""

PLAIN_PUNCTUATION: Final = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
    }
)
"""The curly quotes and dashes a normalized match reads as their plain forms."""


class CitationStatus(StrEnum):
    """What checking one citation found."""

    VERIFIED = "verified"
    VERIFIED_NORMALIZED = "verified_normalized"
    QUOTE_NOT_FOUND = "quote_not_found"
    UNKNOWN_SEGMENT = "unknown_segment"


VERIFIED_STATUSES: Final = frozenset(
    {
        CitationStatus.VERIFIED,
        CitationStatus.VERIFIED_NORMALIZED,
    }
)
"""The statuses of a citation whose quote was found."""


class CitationCheck(BaseModel):
    """One citation as cited, what checking it found, and where it really is.

    A verified check holds the anchor it built from the extraction, and how
    many times its quote occurs in the segment; the anchor locates the first.
    A failed check holds no anchor.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: CitationStatus
    segment_id: str
    quote: str
    occurrences: int = Field(default=0, ge=0)
    anchor: SourceAnchor | None = None

    @model_validator(mode="after")
    def require_consistency(
        self,
    ) -> "CitationCheck":
        """Require an anchor and an occurrence exactly when the quote was found."""

        status = self.status.value

        if self.status in VERIFIED_STATUSES:
            if self.anchor is None:
                raise ValueError(
                    f"A citation check with status {status} holds the anchor it verified."
                )

            if self.occurrences < 1:
                raise ValueError(
                    f"A citation check with status {status} found its quote at least once."
                )

        else:
            if self.anchor is not None:
                raise ValueError(f"A citation check with status {status} holds no anchor.")

            if self.occurrences != 0:
                raise ValueError(f"A citation check with status {status} found no occurrences.")

        return self

    @model_serializer(mode="wrap")
    def omit_absent_anchor(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """Leave out the anchor of a check that found none."""

        data = cast(dict[str, JsonValue], handler(self))

        if self.anchor is None:
            data.pop("anchor", None)

        return data


def verify_citation(
    segmented: SegmentedText,
    *,
    segment_id: str,
    quote: str,
    origin: InputOrigin | None = None,
) -> CitationCheck:
    """Check one quote against the segment of an extraction it cites.

    The quote is looked for in the cited segment exactly, and then, if not
    found, after normalizing both: Unicode NFC, curly quotes and dashes read
    as plain ones, every run of whitespace as one space, and the quote's own
    surrounding whitespace dropped. Matching is case-sensitive.

    A found quote is anchored at its first occurrence in the segment, by the
    source's own text, with up to 32 code points of the text around it, its
    position in the extraction's text, and, for a segment of a PDF page, the
    page and the box on it. The origin is the source's, as its input
    recorded it.
    """

    segment = segmented.segment(segment_id)

    if segment is None:
        return CitationCheck(
            status=CitationStatus.UNKNOWN_SEGMENT,
            segment_id=segment_id,
            quote=quote,
        )

    found = _find(segmented.segment_text(segment), quote)

    if found is None:
        return CitationCheck(
            status=CitationStatus.QUOTE_NOT_FOUND,
            segment_id=segment_id,
            quote=quote,
        )

    status, start, end, occurrences = found

    return CitationCheck(
        status=status,
        segment_id=segment_id,
        quote=quote,
        occurrences=occurrences,
        anchor=_anchor(
            segmented,
            segment,
            start=segment.start + start,
            end=segment.start + end,
            origin=origin,
        ),
    )


def _find(
    text: str,
    quote: str,
) -> tuple[CitationStatus, int, int, int] | None:
    """Return how a quote was found in a text, where first, and how often, or None."""

    if not quote.strip():
        return None

    if quote in text:
        start = text.index(quote)

        return (
            CitationStatus.VERIFIED,
            start,
            start + len(quote),
            _occurrences(text, quote),
        )

    normalized, positions = _normalize_text(text)
    wanted = _normalize_quote(quote)
    first = normalized.find(wanted)

    if first == -1:
        return None

    return (
        CitationStatus.VERIFIED_NORMALIZED,
        positions[first],
        positions[first + len(wanted) - 1] + 1,
        _occurrences(normalized, wanted),
    )


def _occurrences(
    text: str,
    quote: str,
) -> int:
    """Return how many times a quote starts in a text, overlapping ones included."""

    count = 0
    start = text.find(quote)

    while start != -1:
        count += 1
        start = text.find(quote, start + 1)

    return count


def _normalize_quote(
    quote: str,
) -> str:
    """Return a quote in NFC, with plain punctuation, whitespace collapsed and trimmed."""

    plain = unicodedata.normalize("NFC", quote).translate(PLAIN_PUNCTUATION)

    return " ".join(plain.split())


def _normalize_text(
    text: str,
) -> tuple[str, list[int]]:
    """Return a text with plain punctuation and whitespace collapsed, and where each
    character came from.

    The text is already NFC, so each character of the result maps to one
    character of the text: a run of whitespace to its first character.
    """

    characters: list[str] = []
    positions: list[int] = []
    previous_space = False

    for index, character in enumerate(text):
        if character.isspace():
            if not previous_space:
                characters.append(" ")
                positions.append(index)

            previous_space = True
            continue

        characters.append(character.translate(PLAIN_PUNCTUATION))
        positions.append(index)
        previous_space = False

    return "".join(characters), positions


def _anchor(
    segmented: SegmentedText,
    segment: Segment,
    *,
    start: int,
    end: int,
    origin: InputOrigin | None,
) -> SourceAnchor:
    """Return the anchor of one span of an extraction's text."""

    text = segmented.text
    fragment = _page_fragment(segmented, segment)

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


def _page_fragment(
    segmented: SegmentedText,
    segment: Segment,
) -> FragmentSelector | None:
    """Return the PDF fragment of a segment's page and box, for a segment of a PDF page."""

    if segment.page is None or segmented.media_type != PDF_MEDIA_TYPE:
        return None

    value = f"page={segment.page}"

    if segment.bbox is not None:
        value += f"&viewrect={_viewrect(segment.bbox)}"

    return FragmentSelector(value=value, conformsTo=PDF_FRAGMENT_SPECIFICATION)


def _viewrect(
    box: BoundingBox,
) -> str:
    """Return a box as a viewrect: left, top, width and height, to hundredths of a point."""

    return ",".join(
        _points(value)
        for value in (
            box.left,
            box.top,
            box.width,
            box.height,
        )
    )


def _points(
    value: float,
) -> str:
    """Return a measurement in points, to hundredths, without trailing zeros."""

    return f"{value:.2f}".rstrip("0").rstrip(".")


__all__ = [
    "PLAIN_PUNCTUATION",
    "QUOTE_CONTEXT_LENGTH",
    "VERIFIED_STATUSES",
    "CitationCheck",
    "CitationStatus",
    "verify_citation",
]

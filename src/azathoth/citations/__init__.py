"""Source anchors, segments and citations: where in which content something is (ADR 0113)."""

from azathoth.citations.anchors import (
    Extraction,
    SourceAnchor,
)
from azathoth.citations.segments import (
    SEGMENT_ID,
    BoundingBox,
    ExtractionError,
    Segment,
    SegmentedText,
)
from azathoth.citations.selectors import (
    FRAGMENT_SELECTOR,
    FRAGMENT_SPECIFICATIONS,
    MEDIA_FRAGMENT_SPECIFICATION,
    PDF_FRAGMENT_SPECIFICATION,
    TEXT_POSITION_SELECTOR,
    TEXT_QUOTE_SELECTOR,
    FragmentSelector,
    Selector,
    TextPositionSelector,
    TextQuoteSelector,
)

__all__ = [
    "FRAGMENT_SELECTOR",
    "FRAGMENT_SPECIFICATIONS",
    "MEDIA_FRAGMENT_SPECIFICATION",
    "PDF_FRAGMENT_SPECIFICATION",
    "TEXT_POSITION_SELECTOR",
    "SEGMENT_ID",
    "TEXT_QUOTE_SELECTOR",
    "BoundingBox",
    "Extraction",
    "ExtractionError",
    "FragmentSelector",
    "Segment",
    "SegmentedText",
    "Selector",
    "SourceAnchor",
    "TextPositionSelector",
    "TextQuoteSelector",
]

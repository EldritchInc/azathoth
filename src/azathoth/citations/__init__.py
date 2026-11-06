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
from azathoth.citations.text_segmenter import (
    BLANK_LINES,
    TEXT_SEGMENTER,
    TEXT_SEGMENTER_VERSION,
    segment_text,
)
from azathoth.citations.verification import (
    PLAIN_PUNCTUATION,
    QUOTE_CONTEXT_LENGTH,
    VERIFIED_STATUSES,
    CitationCheck,
    CitationStatus,
    verify_citation,
)

__all__ = [
    "BLANK_LINES",
    "FRAGMENT_SELECTOR",
    "FRAGMENT_SPECIFICATIONS",
    "MEDIA_FRAGMENT_SPECIFICATION",
    "PDF_FRAGMENT_SPECIFICATION",
    "PLAIN_PUNCTUATION",
    "QUOTE_CONTEXT_LENGTH",
    "TEXT_POSITION_SELECTOR",
    "SEGMENT_ID",
    "TEXT_QUOTE_SELECTOR",
    "TEXT_SEGMENTER",
    "TEXT_SEGMENTER_VERSION",
    "VERIFIED_STATUSES",
    "BoundingBox",
    "CitationCheck",
    "CitationStatus",
    "Extraction",
    "ExtractionError",
    "FragmentSelector",
    "Segment",
    "SegmentedText",
    "Selector",
    "SourceAnchor",
    "TextPositionSelector",
    "TextQuoteSelector",
    "segment_text",
    "verify_citation",
]

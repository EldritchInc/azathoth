"""Source anchors and citations: where in exactly which content something is (ADR 0113)."""

from azathoth.citations.anchors import (
    Extraction,
    SourceAnchor,
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
    "TEXT_QUOTE_SELECTOR",
    "Extraction",
    "FragmentSelector",
    "Selector",
    "SourceAnchor",
    "TextPositionSelector",
    "TextQuoteSelector",
]

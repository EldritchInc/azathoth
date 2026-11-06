"""The standard text segmenter: one segment per paragraph (ADR 0113).

Text content is divided at blank lines, so each paragraph is a segment a
model can cite as `s1`, `s2` and so on. The segmenter is deterministic: the
same text always gives the same extraction, and so the same digest.
"""

import re
import unicodedata
from typing import Final

from azathoth.citations.segments import Segment, SegmentedText
from azathoth.inputs import is_text_media_type

TEXT_SEGMENTER: Final = "segment_text"
"""The tool name a text segmenter's extractions record."""

TEXT_SEGMENTER_VERSION: Final = "1"
"""The version of the segmenter's output, raised only when that output changes.

It is not Azathoth's version, so a release that leaves segmentation as it was
leaves every extraction's digest as it was.
"""

BLANK_LINES: Final = re.compile(r"\n(?:[^\S\n]*\n)+")
"""A paragraph break: a line break, then one or more lines holding only whitespace."""


def segment_text(
    text: str,
    *,
    source_digest: str,
    media_type: str = "text/plain",
) -> SegmentedText:
    """Divide text into one segment per paragraph.

    The text is first put in NFC, which the extraction's positions count.
    Paragraphs are separated by blank lines, lines holding only whitespace
    included, and a carriage return before a line break is whitespace like
    any other. A segment spans its paragraph without the whitespace around
    it. Text holding nothing but whitespace has no segments.

    Raises:
        ValueError: The media type is not a text media type.
    """

    if not is_text_media_type(media_type):
        raise ValueError(f"{TEXT_SEGMENTER} segments text/* content; got {media_type!r}.")

    normalized = unicodedata.normalize("NFC", text)

    return SegmentedText(
        tool=TEXT_SEGMENTER,
        version=TEXT_SEGMENTER_VERSION,
        source_digest=source_digest,
        media_type=media_type,
        text=normalized,
        segments=_paragraphs(normalized),
    )


def _paragraphs(
    text: str,
) -> tuple[Segment, ...]:
    """Return one segment per non-blank paragraph of a text, numbered from 1."""

    segments: list[Segment] = []
    bounds: list[tuple[int, int]] = []
    start = 0

    for match in BLANK_LINES.finditer(text):
        bounds.append((start, match.start()))
        start = match.end()

    bounds.append((start, len(text)))

    for chunk_start, chunk_end in bounds:
        chunk = text[chunk_start:chunk_end]
        trimmed = chunk.strip()

        if not trimmed:
            continue

        first = chunk_start + len(chunk) - len(chunk.lstrip())

        segments.append(
            Segment(
                id=f"s{len(segments) + 1}",
                start=first,
                end=first + len(trimmed),
            )
        )

    return tuple(segments)


__all__ = [
    "BLANK_LINES",
    "TEXT_SEGMENTER",
    "TEXT_SEGMENTER_VERSION",
    "segment_text",
]

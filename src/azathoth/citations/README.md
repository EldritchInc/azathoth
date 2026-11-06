# Citations

`azathoth.citations` says where in exactly which content something is, and
checks a citation against it (ADR 0113). Places are written as W3C Web
Annotation selectors, under the model's own names, so an annotation tool
reads them as they stand.

```python
from azathoth.citations import (
    PDF_FRAGMENT_SPECIFICATION,
    Extraction,
    FragmentSelector,
    SourceAnchor,
    TextPositionSelector,
    TextQuoteSelector,
)
```

## Selectors

- `TextQuoteSelector`: the `exact` text cited, never empty, with a `prefix`
  and a `suffix` of the text around it.
- `TextPositionSelector`: the `start` and `end` of the text cited, in
  Unicode code points; `start` is included and `end` is not, and the span is
  never empty.
- `FragmentSelector`: a fragment `value`, without its `#`, and the
  specification it `conformsTo`: `PDF_FRAGMENT_SPECIFICATION`
  (`http://tools.ietf.org/rfc/rfc3778`, for `page=` and `viewrect=`) or
  `MEDIA_FRAGMENT_SPECIFICATION` (`http://www.w3.org/TR/media-frags/`, for
  `xywh=`).

`Selector` is the union of the three, read by its `type`.

## Source Anchors

A `SourceAnchor` is one place in one exact piece of content: its `digest`
and `media_type`, the `origin` where the content durably lives when one is
known, one to three `selectors` of different kinds, and the `extraction`
whose text the text selectors count.

An `Extraction` names a tool, its version, and the digest of its output in
the content store, so an anchor can be checked again against the very text
it was made from. Text selectors always count an extraction's text, so an
anchor holding one names its extraction. A quote and a position in one anchor
must select text of the same length, and a fragment must suit the content: a
PDF fragment for a PDF, a media fragment for an image.

An anchor's dump leaves out an `origin` and an `extraction` it does not have.

## Segments

A document tool divides content into segments, and its whole output is a
`SegmentedText`: the tool and its version, the source's digest and media
type, the text it extracted, and its `Segment`s.

- A segment's `id` is `s<N>`, or `p<PAGE>.s<N>` on a page, counting from 1.
- `start` and `end` count code points of the extraction's text, `start`
  included and `end` not.
- A segment on a page names its `page`, and may name its `bbox`, a
  `BoundingBox` of `left`, `top`, `width` and `height` in points from the
  page's top-left corner.

The text is in NFC. Segments are in order, do not overlap, lie within the
text and are named once each. A source with no text has no segments.

`segment(id)` finds a segment and `segment_text(segment)` returns what it
spans. `canonical_bytes()` is the canonical JSON the content store keeps,
with sorted keys and no padding, and `digest()` names it. `extraction()`
returns the `Extraction` an anchor made from the text names, and
`store(store)` keeps the JSON. `SegmentedText.load(store, digest)` reads it
back, returns `None` when the store lacks it, and raises `ExtractionError`
when the content there is not a segmented text.

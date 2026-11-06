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

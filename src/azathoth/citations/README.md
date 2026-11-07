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

An extraction of a paged source may list its `pages`, each a `SourcePage`
of its `page` number, its `width` and `height` in points as it is shown,
and `has_text`, whether any segment is on it (ADR 0114). Listed pages run
from 1 in order, every segment is on one of them, and a page has text
exactly when a segment is on it. `page(number)` finds one. An extraction
that lists no pages leaves them out of its JSON, so its digest is what it
was before pages could be listed.

`segment(id)` finds a segment and `segment_text(segment)` returns what it
spans. `canonical_bytes()` is the canonical JSON the content store keeps,
with sorted keys and no padding, and `digest()` names it. `extraction()`
returns the `Extraction` an anchor made from the text names, and
`store(store)` keeps the JSON. `SegmentedText.load(store, digest)` reads it
back, returns `None` when the store lacks it, and raises `ExtractionError`
when the content there is not a segmented text.

`handle()` returns the `ExtractionHandle` a step outputs in its place (ADR
0114): `{"extraction": {"tool", "version", "digest", "source_digest",
"media_type"}}`, as `to_value()` gives it. `extraction_handle_from_value`
reads one back, and returns `None` for any value that is not exactly one.
`extraction()` gives the `Extraction` an anchor names.

## Checking Citations

`verify_citation(segmented, segment_id=..., quote=..., origin=...)` checks
one citation against the segment it names, and only that segment, and
returns a `CitationCheck`: the `status`, the `segment_id` and `quote` as
cited, how many `occurrences` of the quote the segment holds, and, when it
was found, the `anchor`.

`CitationStatus` is one of:

- `verified`, found exactly;
- `verified_normalized`, found once both are normalized: NFC, curly quotes
  and dashes as plain ones (`PLAIN_PUNCTUATION`), whitespace runs as one
  space, and the quote trimmed. Matching is case-sensitive;
- `quote_not_found`, not in the segment, or empty;
- `unknown_segment`, no segment of that ID.

A found quote is anchored at its first occurrence by the source's own text,
with up to `QUOTE_CONTEXT_LENGTH` (32) code points of the extraction's text
around it, its position, and, on a PDF page, a fragment of the page and its
box as a `viewrect`. `VERIFIED_STATUSES` are the two found statuses. A check
holds an anchor and at least one occurrence exactly when it is one of them.

## Segmenting Text

`segment_text(text, source_digest=..., media_type=...)` makes one segment
per paragraph of `text/*` content, `s1` onwards. The text is first put in
NFC. Paragraphs are separated by blank lines, a line of only whitespace
included, and each segment spans its paragraph without the whitespace around
it. The extraction records `TEXT_SEGMENTER` (`segment_text`) and
`TEXT_SEGMENTER_VERSION`, raised only when its output changes, so the same
text always gives the same digest.

```python
from azathoth.citations import segment_text, verify_citation
from azathoth.inputs import content_bytes_digest

text = "Claim 0412.\n\nThe claim was received on December 14."
segmented = segment_text(text, source_digest=content_bytes_digest(text.encode()))

check = verify_citation(segmented, segment_id="s2", quote="received on December 14")
```

## Exporting Citations

`citation_annotations(run_id, records, generator=...)` returns every
verified check of a run's `CitationRecord`s (each a step's ID, its record's
digest and the checks it holds) as one W3C Web Annotation
`AnnotationCollection` (ADR 0117), in the `WEB_ANNOTATION_CONTEXT`. Each
verified check with an anchor is an `Annotation` `highlighting` its
anchor's place: its target's source is `anchor_source(anchor)`, the
origin's URI, with an S3 `versionId` query when the origin names a version,
or else `content_uri(digest)`, the content's RFC 6920 `ni:` URI
(`CONTENT_URI_PREFIX`); its selectors are the anchor's. Its body names the
step and run, and what a provider's citation supports; its generator is
the given name, with `AZATHOTH_HOMEPAGE`. Every `id` is a `urn:uuid:` of a
name-based UUID in `ANNOTATION_NAMESPACE`, so the same checks always give
the same collection. Unverified checks are left out and counted in the
label, and a collection with nothing in it has no page.

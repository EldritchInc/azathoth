# ADR 0113: Anchor and Verify Citations

- Status: Accepted
- Date: 2026-11-05
- Decided in: #138

## Context

Azathoth 1.3 takes documents in and gives evidence out. A workflow can now
be given a PDF or an image, kept by the digest of its bytes, with the origin
it came from (ADR 0112). What it cannot yet do is say *where* in that
content a result came from, in a form a reviewer's tools can open, and check
that the place really says what a model claims.

A model's own account of where it read something cannot be trusted: a page
number or a quote written by a model is generated text like any other.
Azathoth therefore locates, and the model only cites. A deterministic tool
divides a document into segments, each with its place in the document; a
cited step names segments and quotes them; and Azathoth checks each quote
against the segment it names, and records where it really is.

This decision is the part of that design that involves no model: how a
place in content is written down, and how a citation is checked. Reading
PDFs into segments, prompting a cited step, and recording its checks are
later decisions of 1.3.

## Decision

### Places are written as W3C Web Annotation selectors

A place in content is written with the selectors of the W3C Web Annotation
Data Model, under the model's own names, so a reviewer's annotation tools
read them as they stand:

- a `TextQuoteSelector` holds the `exact` text cited, with a `prefix` and a
  `suffix` of the text around it;
- a `TextPositionSelector` holds the `start` and `end` of the text cited;
- a `FragmentSelector` holds a fragment of the document, its `value`, and
  the specification it `conformsTo`.

```json
[
  {"type": "TextQuoteSelector", "exact": "received on December 14", "prefix": "was ", "suffix": ", 2026"},
  {"type": "TextPositionSelector", "start": 18234, "end": 18257},
  {"type": "FragmentSelector", "value": "page=3", "conformsTo": "http://tools.ietf.org/rfc/rfc3778"}
]
```

Positions count Unicode code points, as the Web Annotation model says:
`start` is included and `end` is not. A JavaScript highlighter counts UTF-16
code units, which differ from code points beyond the Basic Multilingual
Plane, such as emoji; converting between them is the business of whatever
exports anchors to such a tool, never of the stored anchor.

Two fragment specifications are accepted:

- `http://tools.ietf.org/rfc/rfc3778`, for a page or a rectangle of a PDF
  (`page=3`, `page=3&viewrect=…`). RFC 8118 has replaced RFC 3778 and keeps
  the same parameters; the Web Annotation model's table names RFC 3778, and
  that is the IRI annotation tools look for.
- `http://www.w3.org/TR/media-frags/`, for a region of an image
  (`xywh=160,120,320,240`).

A fragment's value is written without the `#` that introduces it in a URI.

The model's field `conformsTo` keeps its own name, the one camel-case name
among Azathoth's fields, rather than a snake-case name translated at export.

### A source anchor

A source anchor is one place in one exact piece of content:

```json
{
  "digest": "<SHA-256 of the content's bytes>",
  "media_type": "application/pdf",
  "origin": {"uri": "s3://claims-intake/2026/11/claim-0412.pdf", "version_id": "3HL4kqtJlcpXroDTDmJ"},
  "selectors": ["…"],
  "extraction": {"tool": "segment_pdf", "version": "1.3.0", "digest": "<SHA-256 of its output>"}
}
```

- `digest` names the bytes, as the content store keeps them (ADR 0096).
- `origin` is where those bytes durably live, as an input recorded it
  (ADR 0112). It is left out when nothing names one.
- `selectors` holds one to three selectors, at most one of each kind.
- `extraction` names the tool, and its version, that produced the text the
  text selectors count, and the digest of the tool's output in the content
  store. An anchor can then be checked again against exactly the text it was
  made from, long after the run.

A PDF's text is not its bytes: it is what a tool extracted from them. So
text selectors always count an extraction's text, and an anchor holding one
names its extraction:

```text
A source anchor's text selectors count the text of an extraction, so the anchor names its extraction.
```

A quote and a position in one anchor must agree on the length of the text
they select:

```text
A source anchor's quote is 23 characters long, but its position spans 5.
```

A fragment must be one its content's media type can have: a PDF fragment
for a PDF, a media fragment for an image.

```text
A FragmentSelector conforming to http://tools.ietf.org/rfc/rfc3778 cannot locate image/png content.
```

### Segments, and the extraction that stores them

A document tool divides content into segments: spans of the text it
extracted, each with an ID a model cites. Its whole output is a segmented
text: the tool and its version, the source's digest and media type, the
text, and the segments in order.

```json
{
  "tool": "segment_pdf",
  "version": "1.3.0",
  "source_digest": "<SHA-256 of the PDF>",
  "media_type": "application/pdf",
  "text": "…",
  "segments": [
    {"id": "p3.s12", "start": 18234, "end": 18311, "page": 3, "bbox": {"left": 72.0, "top": 144.5, "width": 310.25, "height": 14.0}}
  ]
}
```

- A segment's ID is `s<N>`, or `p<PAGE>.s<N>` for a segment on a page,
  counting from 1. IDs are unique within one extraction, and short enough
  to cite in a prompt; an anchor always names its extraction, so they never
  need to be unique beyond it.
- `start` and `end` count Unicode code points of the extraction's text,
  `start` included and `end` not, as selectors do. Segments are in order, do
  not overlap, and lie within the text.
- A segment on a page names its page, and may name its bounding box: a
  rectangle in points from the page's top-left corner, the frame a PDF
  fragment's `viewrect` uses.
- A source with no text, such as a scanned page with no text layer, has no
  segments: its text is never guessed.

The text is in Unicode normalization form NFC, which the Web Annotation
model asks of the text positions count, so a position counts what a reader
sees rather than how it happened to be encoded:

```text
An extraction's text is in Unicode normalization form NFC.
```

A segmented text is stored in the content store as canonical JSON, with
sorted keys and no insignificant whitespace, so the same output always has
the same digest. That digest is the extraction's identity: the `digest` of
an anchor's `extraction`. Any anchor can then be checked again, from the
content store alone, against exactly the text it was made from.

### Checking a citation

A citation names a segment and quotes it. Azathoth looks for the quote in
that segment only, never elsewhere in the document, so a citation cannot
borrow a sentence from a page it does not name. Checking it records one of
four statuses:

- `verified`: the quote is in the segment exactly;
- `verified_normalized`: the quote is in the segment once both are
  normalized, as described below;
- `quote_not_found`: the segment exists, and the quote is not in it, or is
  empty;
- `unknown_segment`: the extraction has no segment of that ID.

Models routinely re-flow whitespace and straighten punctuation, so a
check that demanded byte-for-byte equality would fail citations that are
plainly right. One normalization is applied, and only after an exact search
fails: Unicode NFC; curly quotes as plain `'` and `"`, and dashes and the
minus sign as `-`; every run of whitespace, line breaks and non-breaking
spaces included, as one space; and the quote's own surrounding whitespace
dropped. Matching stays case-sensitive: a change of case can change
meaning. A normalized match has its own status, so a step can still demand
exact quotes.

A found quote is anchored at its first occurrence in the segment, and the
check records how many times the quote occurs there. The anchor holds the
source's own text, never the quote as cited:

- a `TextQuoteSelector` with the source's exact text, and up to 32 Unicode
  code points before and after it, from the extraction's whole text rather
  than the segment alone, as a reader's tool searches the whole document;
- a `TextPositionSelector` with its span in the extraction's text;
- for a segment of a PDF page, a `FragmentSelector` naming the page, and the
  segment's box as a `viewrect`, in points to the hundredth:

```json
{"type": "FragmentSelector", "value": "page=3&viewrect=72,144.5,310.25,14", "conformsTo": "http://tools.ietf.org/rfc/rfc3778"}
```

The origin is the one the source's input recorded (ADR 0112). It is given to
the check by whoever checks it; neither the citation nor the extraction
holds it.

A check is recorded as it was cited and as it was found:

```json
{
  "status": "verified_normalized",
  "segment_id": "p3.s12",
  "quote": "received on December 14",
  "occurrences": 1,
  "anchor": {"…": "…"}
}
```

A failed check holds no anchor and no occurrences.

## Consequences

- Places in content have one shape everywhere they will be recorded: in run
  evidence, in the values a cited step returns, in `invocation show` and
  over MCP.
- A process tool reading a cited value reads standard selectors, in plain
  JSON, with no Azathoth import.
- Nothing is recorded yet. The models and the check are the vocabulary
  the later decisions of 1.3 record. Whatever records a check must not take
  a citation a tool or a model returns as verified on its word: it checks
  it again against the stored extraction, by digest.

## Alternatives Considered

### Snake-case fields, translated at export

Rejected. Every anchor in every run's evidence would use names no
annotation tool knows, and every export would translate them back. One
camel-case field is the smaller cost.

### RFC 8118's IRI for PDF fragments

Rejected for now. RFC 8118 is the current definition of PDF fragments, but
the Web Annotation model lists RFC 3778, and a tool matching the listed IRI
would not recognize another. The parameters are the same under either.

### Anchors that hold a page number from the model

Rejected. A page number a model writes is generated text. Azathoth records
where a quote is from the extraction that located it, never from what a
model says about it.

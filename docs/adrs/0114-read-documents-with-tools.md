# ADR 0114: Read Documents with Tools

- Status: Accepted
- Date: 2026-11-06
- Decided in: #139

## Context

A workflow can be given a PDF or an image, kept in the content store and
named by a content handle (ADR 0112), and Azathoth can check a citation
against the segments an extraction holds (ADR 0113). Between the two, a tool
must read the document and divide it into segments.

No tool could read a document. A process tool runs with none of Azathoth's
environment (ADR 0099), so it has no way into the content store; the
in-process Python runtime runs a fixed set of builtins and imports nothing.
A handle gave a tool a digest it could do nothing with.

The handle's own rule was not yet enforced either. ADR 0112 decided that a
handle is honoured only when its digest was recorded by a
`workflow.input.resolved` event of the run or of a run in its lineage. Until
something read content through a handle, nothing needed to check.

## Decision

### Content inputs

A process implementation may name some of its inputs content inputs:

```json
"content_inputs": ["document"]
```

Before the tool runs, the engine requires each one to be exactly a content
handle, and to name content the run received. It reads the bytes from the
content store, checks them against their digest, and writes them to a file
of their own, named for the input and given its media type's extension, in a
temporary folder. The tool is given the file in place of the handle:

```json
{"document": {"path": "/tmp/azathoth-content-.../document.pdf", "digest": "<SHA-256>", "media_type": "application/pdf", "size_bytes": 482113}}
```

The folder is removed once the tool is done, whether it succeeded or not.

A file, rather than the bytes in the tool's standard input, keeps a tool's
input small, lets it hand the path to a library that opens files, and works
alike on every platform.

### The engine reads the store; a tool never does

A tool is given content, never access to it. It needs no database path and
no cloud credential to read a document, and a tool from anyone, a document
tool of a third party's included, can read only the content its step was
given. The engine checks a handle once, for every tool, in one place.

### What a run received

A run received the content its initial context records: each
`workflow.input.resolved` event's digest, under the media type it records.
A child run received that, and everything every run above it in its lineage
received, read from their initial contexts in turn up to the root
(ADR 0104). Only initial contexts count. They are written by the entry point
that starts the run; an event a step adds while the run is under way claims
nothing.

A run's initial context is read from its journal (ADR 0105), which records
the context a run started from whether the run is still under way, as a
parent waiting on its child is, or long finished. A run whose journal is not
known ends the walk, as does a lineage that loops back, and no more runs are
read than workflows may nest.

A handle is refused when it names content the run never received, names it
under another media type than the one received, or names another size than
the content holds:

```text
Content input 'document' of tool segment_pdf names content <SHA-256>, which this run never received.
```

```text
Content input 'document' of tool segment_pdf names content <SHA-256> as image/png, but this run received it as application/pdf.
```

Content the store lacks, or holds under a digest its bytes do not have, is
refused too:

```text
Content <SHA-256> in the content store does not match its digest.
```

### Every entry point gives it

`workflow run`, `workflow invoke`, `job run`, the worker, resumed runs and
the MCP server each give their runs' tools the content store and journal
they already keep. A runner given no content access, as a benchmark's is,
refuses a tool that takes content inputs:

```text
Tool segment_pdf takes content inputs, which this run cannot give: it has no content store.
```

Only process implementations take content inputs. An implementation without
them serializes as it always has, so its digest is unchanged.

### Extraction outputs

A document tool's work is an extraction: the text it took from a document,
divided into segments (ADR 0113). An implementation with content inputs may
name the output that holds it:

```json
"extraction_output": "extraction"
```

The engine requires that output to be a segmented text, and checks it
against what the tool was given: its source must be one of the tool's
content inputs, under the media type it was given, and it must name the tool
that made it. A tool that claims to have extracted content it was never
given is refused:

```text
Tool segment_pdf returned an extraction of content <SHA-256>, which it was not given.
```

```text
Tool segment_pdf returned an extraction that names the tool segment_text.
```

An extraction that passes is kept in the content store, as the canonical
JSON whose digest names it, and the output is replaced by an extraction
handle naming it, as a content handle names content:

```json
{"extraction": {"tool": "segment_pdf", "version": "1", "digest": "<SHA-256 of the extraction>", "source_digest": "<SHA-256 of the PDF>", "media_type": "application/pdf"}}
```

Its text and segments stay in the store. A whole document's text does not
travel through every event, every step's output and every child's input.

The extraction is recorded as a resource of the step that made it, beside
the tool's own:

```json
{"kind": "extraction", "identifier": "<SHA-256 of the extraction>", "attributes": {"tool": "segment_pdf", "version": "1", "source_digest": "<SHA-256 of the PDF>", "media_type": "application/pdf", "segments": 214}}
```

A step's resources are written by the engine's own strategies, never by a
tool, a model or a workflow document, and are kept in the run's journal and
its record. That record, not the store, is what says an extraction was made:
the store is content-addressed and shared, and anything can be put in it as
an input. Whatever checks citations against an extraction requires that
record in the run's lineage, as a content input requires a run to have
received its content.

### A standard tool to segment PDFs

The standard library gains `segment_pdf`, the first document tool, with its
identifiers from a range of its own, `c4000000-…`. It takes one content
input, `document`, and names one extraction output, `extraction`. It reads
PDFs with pdfminer.six, under the MIT license, which a new extra installs:

```bash
python -m pip install "azathoth-ai[documents]"
```

A step that runs it without the extra fails, with status 1:

```text
segment_pdf needs pdfminer.six, which is not installed; install azathoth-ai[documents].
```

pdfminer.six lays each page out, and each text box with text is one
segment, `p<PAGE>.s<N>` from 1 on each page. A box is a unit a reader sees
as one: a paragraph, a heading, a cell of a form. The layout's parameters
change which boxes there are, so the extraction's version names them, with
the tool's version and pdfminer.six's:

```text
1.0.0 (pdfminer.six 20260107; line_overlap=0.5,char_margin=2.0,line_margin=0.5,word_margin=0.1,boxes_flow=0.5)
```

The text is the page's: the ligatures U+FB00 to U+FB06 are written out as
their letters, so a model's plain quote is found, and nothing else is
changed. A hyphen at the end of a line stays, since only a dictionary could
say whether it splits a word.

A box is converted from pdfminer's frame, points from the lower-left corner
of the media box, to RFC 8118's, points from the top-left corner of the crop
box, and clipped to the crop box. A rotated page is laid out as it is shown,
in a frame RFC 8118 does not settle, so its segments name their page and no
box; so does a segment outside the crop box. A citation of either names the
page alone.

The image the container builds installs the extra, with the cloud ones.

## Consequences

- A handle passes between steps, to tools, and to child workflows as plain
  JSON, as before; only a content input turns it into a file, and only after
  the check.
- A child workflow given a handle by its parent reads the parent's document:
  the parent's journal records that it received it.
- Knowing a digest is not enough to read the content it names, though the
  content store is shared by every run of a database.
- Reading the bytes and writing the file happen off the event loop, so a
  large document does not hold up the steps running beside it, and so does
  keeping an extraction.
- A document tool never writes the content store. What it extracted is
  checked and kept by the engine, under its own digest, and the step that
  made it says so.
- A workflow can divide a PDF into citable segments with no tool of its
  own, once the `documents` extra is installed.
- The same PDF segments to the same extraction, and digest, only under the
  same tool, pdfminer.six and layout; a new pdfminer.six is a new version.
- A page with no text layer, such as a scan, has no segments. Reading it
  needs a tool that recognizes text.

## Alternatives Considered

### Grant document tools the store's credentials

Rejected. A tool could then be given `AZATHOTH_DATABASE`, or AWS
credentials for an S3 store, and fetch content itself through a command such
as `azathoth content get`. Every document tool would hold credentials to
every document of the database, and each would have to check the handle's
rule for itself.

### Give the bytes on standard input, as base64

Rejected. A document of ten megabytes would become more than thirteen of
JSON, and most document libraries open a file rather than a buffer.

### Record an extraction as a context event

Rejected. A strategy can add events to a run's context, and one of them
lets a step choose the event's type. A resource of a step is written only by
the strategy that ran it, so it is the stronger record.

### Pass the extraction itself as the step's output

Rejected. A long document's text would be copied into the step's output,
the context, the journal and every child's input. A handle keeps the text in
one place, as a content handle does for the bytes.

### Trust a handle whose content is in the store

Rejected. The store is content-addressed and shared, so content being there
says only that some run received it, not that this one did.

### Read PDFs with PyMuPDF, or with pypdf

Rejected. PyMuPDF is licensed under the AGPL, which every user of Azathoth
would inherit. pypdf extracts a page's text, but not the boxes it lies in,
so a segment could name only its page.

### Segment by page, or by line

Rejected. A page is too long to cite precisely, and a line too short to
hold a claim. A text box is the unit the layout already finds.

### Join a word hyphenated across lines

Rejected. Whether `re-` and `viewed` are one word is a guess, and a guess
would make the text differ from the page a reader checks it against.

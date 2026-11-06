# ADR 0112: Accept Binary Inputs

- Status: Accepted
- Date: 2026-11-05
- Decided in: #137

## Context

Azathoth 1.3 takes documents in and gives evidence out. Its first step is
letting a workflow's input be a document: a PDF, or an image someone
photographed or scanned. Until now, an input's media type was JSON or
`text/*` (ADR 0096), and its content was decoded into the value the workflow
receives, recorded in the run's `workflow.input.received` event.

Binary content cannot be decoded into a JSON value, and should not be copied
into every event and every child workflow's input. The content store already
keeps every referenced input's bytes by their SHA-256 digest (ADR 0096), so
a document needs only to be named, once its bytes are kept.

Later decisions of 1.3 build on this one: source anchors and citation
checks, the standard document tools, and multimodal prompts. None of them is
decided here.

## Decision

### Four binary media types

Azathoth accepts four binary media types, besides JSON and `text/*`:
`application/pdf`, `image/png`, `image/jpeg` and `image/webp`. Any other is
refused, naming what is accepted:

```text
Media type 'image/gif' is not supported; Azathoth accepts application/json, text/* media types, application/pdf, image/jpeg, image/png and image/webp.
```

A file's extension implies its media type, as before: `.pdf`, `.png`,
`.jpg`, `.jpeg` and `.webp` join `.json`, `.txt`, `.md`, `.markdown` and
`.csv`.

Audio and video wait for 1.5.

### Content must match its media type

A declared media type is checked against the content's own signature before
the content is kept. A PDF must hold its `%PDF-` header within its first
1024 bytes, which is where PDF readers look for it; a PNG must start with
its eight-byte signature; a JPEG with its start-of-image marker; and a WebP
must be a RIFF container holding `WEBP`. Content that does not match is
refused, and nothing is stored:

```text
Content is not application/pdf: no PDF header in its first 1024 bytes.
```

```text
Content is not image/png: it does not start with the PNG signature.
```

```text
Content is not image/jpeg: it does not start with a JPEG start-of-image marker.
```

```text
Content is not image/webp: it is not a RIFF container holding WEBP.
```

This catches a file given the wrong name, or the wrong `--media-type`. It
does not check that the document is well formed; the document tools do that
when they read it.

### A workflow receives a content handle

A binary input is never decoded. Its bytes are kept in the content store,
and the workflow receives a content handle naming them:

```json
{
  "content": {
    "digest": "<SHA-256 of the bytes>",
    "media_type": "application/pdf",
    "size_bytes": 482113
  }
}
```

The handle is the value of the run's `workflow.input.received` event. It
passes to a child workflow or a tool as any other JSON value does, and the
bytes stay in the store.

Where the content came from is not part of the handle. As for any referenced
input, a `workflow.input.resolved` event records the reference's URI, the
media type, the size and the digest (ADR 0096).

### A handle names content; it does not grant it

The store is content-addressed, so anyone who knows a digest can write a
handle that names it. A step that reads content through a handle, as
multimodal prompts and the document tools will, honours it only when the
digest was recorded by a `workflow.input.resolved` event of its own run or
of a run in its lineage (ADR 0104). A handle found anywhere else names
content that run never received, and is refused.

### References, within the cap that already applies

Binary content may be given by reference, by `file://` from the CLI and by
`s3://` to a worker, exactly as text is. The policy's cap applies to every
input, so a worker's `--max-input-bytes` (ADR 0108) and the CLI's default of
10 MiB bound documents too. No cap of its own is added: a document beyond the
cap is refused as any input is.

### Inline content, as base64

A job envelope's inline input may hold binary content, as standard base64
(RFC 4648): the standard alphabet, padded, with no whitespace and no `data:`
prefix. The media type says the value is base64; no other key does.

```json
{"value": "JVBERi0xLjcK...", "media_type": "application/pdf"}
```

Anything else is refused when the input is read:

```text
An inline application/pdf input must hold its content as a base64 string.
```

```text
An inline application/pdf input must hold standard base64, padded, with no whitespace.
```

The value is decoded only when the input is resolved, under the policy that
receives it. Its encoded length is checked first, four characters for every
three bytes the cap allows, so a value far beyond the cap is refused without
being decoded; its decoded size is checked after. The cap is the same as for
references:

```text
Inline input is larger than the limit of 10485760 bytes.
```

Decoded content is checked against its media type's signature, stored, and
given to the workflow as a content handle, as a reference's is.

### An inline input may name its origin

An inline input may name where its content durably lives, so that evidence
can point back to it. This matters most where inputs are inline only, as
they are over MCP (ADR 0111): a document sent by value still names the
sender's own copy.

```json
{
  "value": "JVBERi0xLjcK...",
  "media_type": "application/pdf",
  "origin": {
    "uri": "s3://claims-intake/2026/11/claim-0412.pdf",
    "version_id": "3HL4kqtJlcpXroDTDmJ",
    "etag": "9b2cf535f27731c9"
  }
}
```

An origin's `uri` is an absolute URI with a scheme, with no fragment, of at
most 2048 characters. Only an `s3://` origin may name a `version_id` and an
`etag`:

```text
An origin's version_id and etag name an S3 object version; 'https://docs.example.com/claims/0412' is not an s3:// URI.
```

An origin is recorded as given, never read: Azathoth does not check that it
holds the same bytes. A reference is its own origin, so it names none:

```text
A reference is its own origin; 'origin' is given only with an inline 'value'.
```

An origin is part of a request's digest (ADR 0097). A request that names
none digests exactly as it did before inputs could name one.

### The provenance of an inline input

An inline input that is binary, or that names an origin, is recorded by a
`workflow.input.resolved` event, as a reference is. Its provenance has no
URI. It says `"inline": true` instead, and names the origin it was given:

```json
{
  "inline": true,
  "origin": {"uri": "s3://claims-intake/2026/11/claim-0412.pdf"},
  "media_type": "application/pdf",
  "size_bytes": 482113,
  "digest": "<SHA-256 of the bytes>"
}
```

Its content is stored, so the digest names bytes the store holds. Binary
content is stored as decoded. A JSON or text value naming an origin is stored
as the bytes its origin would be compared with: text as UTF-8, and JSON in
its canonical form, with keys sorted and no insignificant whitespace.

An inline JSON or text input that names no origin adds no event and stores
nothing, exactly as before. A reference's provenance records exactly what it
always has.

## Consequences

- A PDF or image can be the input of `workflow run` and `workflow invoke`,
  and of a job envelope by `s3://` or inline. Nothing yet reads it: a prompt that
  binds the workflow input renders the handle as JSON, as it renders any
  value.
- The database schema is unchanged. Binary content is stored in
  `content_blobs`, as text content is, and an inline input's provenance is
  an event payload, which gains only fields that are left out when absent.
- Text and JSON inputs resolve exactly as before.
- The standard tools `read_s3_object` and `split_s3_object` still refuse
  binary media types: a document inside a workflow will be read by the
  document tools, by digest.

## Alternatives Considered

### Give the workflow the bytes, as base64

Rejected. Every event, every child's input and every tool's standard input
would carry the whole document, and every step would pay to parse it.

### A flat handle, with `digest` at its top level

Rejected. Workflow inputs are ordinary JSON, and a flat object with a
`digest` field is easy to come across by accident. A single `content` key
holding exactly the three fields is not.

### Trust the declared media type

Rejected. A mislabelled file would be found only when a provider or a
document tool failed on it, mid-run, after the input had been accepted and
recorded.

### Mark base64 with an `encoding` key

Rejected. Only binary media types are base64, and every binary media type is.
A key that could say only one thing would be one more way to write an
invalid input.

### Trust an inline input's origin by reading it

Rejected. Checking an origin would need credentials for every system a
sender might name, and would make an inline input as expensive as a
reference. The digest records what was received; the origin, where its
sender says it lives.

### A separate cap for binary content

Rejected for now. The existing cap already bounds what a process reads into
memory, and providers' own limits on documents belong to step selection,
which knows which provider a step will call.

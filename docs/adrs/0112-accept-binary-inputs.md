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

Binary content is given by reference, by `file://` from the CLI and by
`s3://` to a worker, exactly as text is. The policy's cap applies to every
input, so a worker's `--max-input-bytes` (ADR 0108) and the CLI's default of
10 MiB bound documents too. No cap of its own is added: a document beyond the
cap is refused as any input is.

An inline binary input is not accepted yet; give it by reference.

## Consequences

- A PDF or image can be the input of `workflow run` and `workflow invoke`,
  and of a job envelope by `s3://`. Nothing yet reads it: a prompt that
  binds the workflow input renders the handle as JSON, as it renders any
  value.
- The database schema is unchanged. Binary content is stored in
  `content_blobs`, as text content is.
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

### A separate cap for binary content

Rejected for now. The existing cap already bounds what a process reads into
memory, and providers' own limits on documents belong to step selection,
which knows which provider a step will call.

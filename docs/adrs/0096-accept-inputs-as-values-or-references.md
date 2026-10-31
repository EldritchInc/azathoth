# ADR 0096: Accept Inputs as Values or References

- Status: Accepted
- Date: 2026-10-31
- Decided in: #113

## Context

A workflow's external input is one JSON value. The CLI parses it from
`--input`, and every source of input, configured runs, benchmark cases and
production invocations alike, delivers it as one canonical
`workflow.input.received` event whose payload is `{"input": <value>}` (ADR
0067). Steps bind to that event, by name or by context reference, and never
see where the value came from.

That is enough for short JSON, and nothing else. A chapter, a contract or a
transcript has to be pasted into a shell argument, escaped as a JSON string.
The queue worker planned for 1.1 cannot carry large inputs in a message at
all, and multimodal inputs planned for 1.2, PDFs and images, are not JSON.
Each of those needs an input that points at content rather than holding it,
and says what kind of content it is.

If steps resolved references themselves, every tool and prompt would need to
know about URIs, credentials and size limits, and the same input could read
different content on a retry or a resume.

## Decision

An external workflow input is a source of one of two shapes:

```json
{"value": <JSON>, "media_type": "application/json"}
{"uri": "file:///Users/you/chapter.md", "media_type": "text/markdown"}
```

- An **inline value** holds its content. Its `media_type` defaults to
  `application/json`.
- A **reference** names its content by URI and must state its media type.
- The shape is closed: a source has exactly one of `value` and `uri`, and no
  other key than `media_type`.

### Media types

A media type is a lowercase `type/subtype` with no parameters. Azathoth 1.1
accepts:

- `application/json`, whose content is parsed as JSON;
- any `text/*` type, whose content is decoded as UTF-8 into a string.

An inline value with a `text/*` media type must be a string. Any other media
type is rejected; binary media types arrive with multimodal inputs, as
additions to this contract.

### Resolving at the edge

References are resolved before the run starts, by the entry point that
received them. Steps only ever see values, so ADR 0080, ADR 0087 and every
existing tool and prompt are unchanged.

Each URI scheme has a resolver. Azathoth 1.1 ships one, for `file://`. A
`file://` URI must be absolute and name the local host, either with an empty
host or `localhost`.

Each entry point decides which schemes it accepts. The CLI accepts `file://`.
The queue worker planned for 1.1 will accept `s3://` only, from allow-listed
buckets, so a message on a queue can never read the worker's own disk.

Resolved content is capped at 10 MiB (10,485,760 bytes). A resolver stops
reading at the cap, so an oversized input is refused without being loaded.
The cap is a constant for now; it becomes a setting when deployments need
different ones.

A reference that cannot be resolved, because its scheme is not accepted, its
content is missing or too large, or its content does not decode as its media
type, fails at the edge. No run or invocation is started, and the CLI exits
with status 1.

### Content store and provenance

Resolved content is saved, before the run starts, in a content-addressed
store keyed by the lowercase hex SHA-256 digest of its bytes. Identical
content is stored once. The local store is a table in the configured
database; an S3-backed store is planned with the queue worker.

The run's initial context records the resolution. The workflow input event
keeps exactly its current shape, `{"input": <value>}`, holding the decoded
value. When the input was a reference, a `workflow.input.resolved` event
follows it, with the same producer and time:

```json
{"uri": "file:///Users/you/chapter.md", "media_type": "text/markdown", "size_bytes": 18234, "digest": "<SHA-256>"}
```

An inline input adds no event, so every existing run, benchmark case and
production invocation records exactly what it did before. Resuming a run,
planned for 1.1, re-reads the content by digest, never by URI, so it sees
exactly what the run saw.

### The CLI

`workflow run` and `workflow invoke` take a file as their input:

```bash
azathoth workflow run <WORKFLOW_ID> --input-file chapter.md
azathoth workflow invoke <WORKFLOW_ID> --input-file request.json --media-type application/json
```

`--input-file` and `--input` are mutually exclusive. The path is made
absolute and becomes a `file://` reference. Without `--media-type`, the media
type is inferred from the extension: `.json` is `application/json`, `.txt` is
`text/plain`, `.md` and `.markdown` are `text/markdown`, and `.csv` is
`text/csv`. Any other extension needs `--media-type`.

### Not decided here

The versioned job envelope that carries an input to an invocation, with its
kind, version, idempotency key, status, result and error, is a separate
decision (ADR 0097, planned). Benchmark cases keep inline JSON inputs.

## Consequences

### Positive

- Long text and JSON documents are given to a workflow as files, without
  escaping them into a shell argument.
- Steps, prompts and tools are unchanged: they receive values exactly as
  before.
- Every resolved input is traceable to its source, size and digest, and its
  exact content is kept for resume and audit.
- The queue worker, multimodal inputs and an S3-backed store extend this
  contract with new schemes, media types and stores rather than replacing it.

### Negative

- Resolved content is stored in the database, so it grows with every distinct
  input file. Identical content is stored once, and nothing yet removes
  content no longer referenced.
- A reference's content is kept twice: as bytes in the store, and as the
  decoded value in the run's context.
- Only the CLI accepts references until the queue worker lands.

## Alternatives Considered

### Resolve references inside steps

Rejected. Every tool and prompt would have to handle URIs, credentials and
size limits, and a retried or resumed step could read different content from
the first attempt.

### Add the provenance to the workflow input event

Rejected. Every input event would change shape, inline ones included, so
existing runs and benchmark cases would no longer record the same context.
A separate event appears only when there is something to record.

### One allow-list of schemes for every entry point

Rejected. An operator at a terminal may read local files; a message from a
queue must not. Which schemes are safe depends on who supplies the input,
and that is a property of the entry point.

### A configurable size cap now

Deferred. The CLI is the only entry point that accepts references in this
release, and one cap serves it. The cap becomes a setting with the queue
worker, when deployments actually differ.

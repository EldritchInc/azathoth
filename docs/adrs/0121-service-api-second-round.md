# ADR 0121: Service API, Second Round

- Status: Accepted
- Date: 2026-11-10

## Context

The service API of ADR 0120 covers what the command line and azathoth-mcp
did when it was made. The local editor, built on it alone, has found what
else it needs and cannot do without reaching past it: a run given a
document rather than JSON, a check of a workflow document that saves
nothing, the models a step could run on, the runs already made, and a try
of one step of a workflow not yet saved.

Each is assembled from what Azathoth already has. This record adds them to
the provisional API, one section each, without changing what a run, an
import or a model selection means.

## Decision

### A file as a run's input

`RunFile(content, media_type)` stands beside `RunInput(payload)`, and
`runs.run` and `runs.invoke` take either as their input. A file is accepted
as the command line's `--input-file` accepts one (ADR 0096, ADR 0112): JSON
and `text/*` content is decoded into the value the workflow receives, a
leading byte order mark dropped; a PDF, PNG, JPEG or WebP is checked against
its media type's signature, kept in the content store by its digest, and
given to the workflow as a content handle, with a `workflow.input.resolved`
event recording that it was inline, its size and its digest.

A file is checked before anything else, so a refused one starts no run,
records no invocation, and keeps nothing. Its refusal is an
`InvalidArgumentError` carrying the message ADR 0112 gives, such as:

```text
Content is not application/pdf: no PDF header in its first 1024 bytes.
```

A file larger than `MAX_INPUT_FILE_BYTES`, the 10 MB `--input-file` allows,
is refused:

```text
The input file is larger than the limit of 10485760 bytes.
```

A file has no name: nothing a run records would hold one, and a `file://`
URI would name a place the instance never read. An invocation's file is
part of its request, so the same file under the same key replays.

A separate type, rather than a field of `RunInput`, keeps a JSON null, which
is input, apart from a file, which is never mistaken for one.

## Consequences

- The editor can run a workflow on a document someone drops on it, through
  its own server, and the run's evidence is what `--input-file` would have
  recorded.
- A document larger than 10 MB is given by reference, an S3 URI or a file
  the instance can read, as the command line gives one; the API takes no
  reference yet.

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

## Consequences

- A handle passes between steps, to tools, and to child workflows as plain
  JSON, as before; only a content input turns it into a file, and only after
  the check.
- A child workflow given a handle by its parent reads the parent's document:
  the parent's journal records that it received it.
- Knowing a digest is not enough to read the content it names, though the
  content store is shared by every run of a database.
- Reading the bytes and writing the file happen off the event loop, so a
  large document does not hold up the steps running beside it.

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

### Trust a handle whose content is in the store

Rejected. The store is content-addressed and shared, so content being there
says only that some run received it, not that this one did.

# ADR 0110: Split and Read S3 Objects

- Status: Accepted
- Date: 2026-11-03
- Decided in: #128

## Context

A worker resolves inputs of at most 100 MiB, and a step's values live in its
run's journal (ADR 0105, ADR 0108). Data larger than that, such as files of
many gigabytes, goes by pointer: a request names the object, a process tool
splits it into chunk objects, and `map_workflow` runs a child over them
(ADR 0106). ADR 0108 recorded the pattern and left its tools undecided, so
every team would have written its own splitter, with its own bugs at chunk
boundaries.

A map's child also needs to read its chunk. The engine resolves references
only in a run's own input, and a map hands each child an inline item, so a
chunk's URI reaches the child as a plain string.

## Decision

### Two standard tools

The standard library gains `split_s3_object` and `read_s3_object`, as
process tools like the others. Their sources import nothing of Azathoth,
so what they do is fixed by their recorded documents. They import boto3 by
name, which the `worker` extra installs, and without it fail saying so. Each
grants itself `AWS_*` and nothing else, so it uses the region, credentials
and endpoint of the process that runs it, and on ECS the task role's
(ADR 0099).

They check no allow-list. What they may read and write is the credentials'
to decide, as ADR 0108 already holds for tools; the stack grants exactly one
prefix (below).

Bad inputs exit with status 2, and every other failure with status 1, each
in one line that names the tool.

### Splitting

`split_s3_object` takes an object's `uri`, a `destination_prefix` and a
required `max_chunks`. In `lines` mode, the default, a chunk ends just after
a newline and holds as many whole lines as fit in `chunk_bytes`, 5 MiB by
default and at most 100 MiB; a line longer than that is refused rather than
cut. In `bytes` mode every chunk but the last holds exactly `chunk_bytes`.

The source is streamed, never held whole. In `lines` mode one read finds
the boundaries and a second writes the chunks, so a source needing more
than `max_chunks` chunks, or holding a line too long, is refused before
anything is written. Both reads are pinned to the source as the tool first
saw it, by version ID in a versioned bucket and by ETag in any other, and a
source that changes while it is split is refused.

The chunks are written under the folder of the step attempt that writes
them, taken from its lineage (ADR 0104):

```text
<DESTINATION_PREFIX><RUN_ID>/<STEP_ID>/<ATTEMPT>/chunk-000000
```

Every chunk traces back to its run. A resumed attempt writes the same keys
again, and a retried attempt a folder of its own. Outside a workflow step
the tool has no attempt to name, and refuses. Nothing deletes chunks; an S3
lifecycle rule on the prefix expires them.

It returns each chunk's URI, index and size, a list a map runs over as it
is, and the source's URI, ETag, version ID and size, the evidence of exactly
which bytes were split.

### Reading

`read_s3_object` takes a `uri`, a `media_type`, `text/plain` by default, and
`max_bytes`, 10 MiB by default and at most 100 MiB. It reads with one ranged
GET of at most `max_bytes` and one byte more, as the worker reads `s3://`
inputs, so an object past the cap is refused without being read whole. It
decodes as resolved inputs are decoded (ADR 0096), and returns the value with
the object's size, SHA-256 digest and ETag.

The child's journal holds the chunk it read, so a chunk should be no larger
than a run's values should be.

### The stack

The stack's optional `DataBucket` and `DataPrefix` grant the task role
`s3:GetObject` and `s3:PutObject` under that prefix, and nothing more: no
listing, no deleting, and never as a place the worker accepts inputs from
(ADR 0109).

### The example

`examples/large-file` counts the words of a file of any size: split it
into chunks of whole lines, map a child over them that reads its chunk and
counts it, and sum the counts. The AWS guide deploys it.

### Verified without AWS

The tools' logic is tested in their own processes' functions against
botocore's `Stubber`, including a comparison of the line splitter with a
reference over random texts and read sizes, and their refusals through the
process runtime. The example runs end to end against a stand-in for S3 over
HTTP, through real processes and real boto3. The sandbox deployment that
gates each release runs the example against real S3, with a file of at
least 20 MiB.

## Consequences

### Positive

- Data of any size is processed from S3 with standard tools, with only URIs
  and small results passing between steps.
- Every chunk names the run and attempt that wrote it, and every split
  records exactly which version of its source it read.
- The tools' behavior is fixed by their documents, whatever Azathoth version
  runs them.

### Negative

- `lines` mode reads its source twice, so a large split costs twice the
  reads of one pass.
- A split in `bytes` mode whose source changes mid-split leaves the chunks
  it already wrote; they are never referenced, and the lifecycle rule
  removes them.
- A map's children run in their parent's task, so one large file is worked
  by one worker, `max_concurrency` children at a time.
- The tools' first meeting with real S3 is the sandbox deployment.

## Alternatives Considered

### Resolve references in a map's items

Rejected. A child would get its chunk as a resolved input, but the engine
would have to resolve values inside items it otherwise passes through
untouched, and every chunk would be stored again in the content store.

### Split in one pass, writing as it goes

Rejected for `lines` mode. A source that turned out to need too many
chunks, or held a line too long, would leave a partial set of chunks behind
it. Reading twice is cheap inside a region; a broken set of chunks is not.

### Hold chunks in temporary files

Rejected. A task's disk is small and ephemeral, and the chunks belong in S3
anyway, where the children read them.

### Check an allow-list in the tools

Rejected. The tools would repeat what IAM already enforces, and a list in
a tool's settings is only as trustworthy as the workflow that sets it.

### Server-side copies of byte ranges

Deferred. S3 can copy a byte range of one object into another without the
tool reading it, with `UploadPartCopy`. In `lines` mode the tool must read
the source anyway to find its boundaries, so it would save only the second
read; in `bytes` mode it would save both. It waits for a workload where the
reads cost enough to matter.

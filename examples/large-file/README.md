# Counting the Words of a Large File

This example counts the words of a text file in S3 of any size, in chunks
(ADR 0110). It shows how a workflow works with data larger than an input
may be:

```text
count-words-in-large-file    split_s3_object  →  map_workflow  →  sum_results
                                                     │
count-words-in-chunk             json_select  →  read_s3_object  →  word_count_process
```

- `split_s3_object` streams the file into chunks of whole lines, each at
  most 1 MiB, under `s3://azathoth-data/work/chunks/`, in the folder of
  the step attempt that wrote them.
- `map_workflow` runs `count-words-in-chunk` once per chunk, four at a time.
  Each child receives its chunk's entry, `{"uri", "index", "size_bytes"}`,
  as its item.
- Each child selects its chunk's URI, reads the chunk as text with
  `read_s3_object`, and counts its words with `word_count_process` from
  [`examples/tools`](../tools/word-count-process.json).
- [`sum-results.json`](tools/sum-results.json), a process tool of this
  example's own, adds the children's counts.

Only URIs and counts pass between steps; each child's run holds its own
chunk's text, at most 1 MiB, and no run holds the whole file.

## Files

| File | What it is |
| --- | --- |
| [`workflows/count-words-in-large-file.json`](workflows/count-words-in-large-file.json) | The parent: split, map, sum. Its input is the file's `s3://` URI. |
| [`workflows/count-words-in-chunk.json`](workflows/count-words-in-chunk.json) | The child a map runs for each chunk. |
| [`tools/sum-results.json`](tools/sum-results.json) | Adds the `result` of every child. |
| [`request.json`](request.json) | A job request for the parent, for a worker's queue. |

## Running It

It runs wherever its tools reach S3: on the stack of
[Running Azathoth on AWS](../../docs/aws.md#data-larger-than-the-cap), which
grants the workers `s3://azathoth-data/work/`, or on any machine whose AWS
credentials may read and write there. The S3 tools need the `worker` extra.
The bucket is the guide's example; use your own, and change the parent's
`destination_prefix` and the request's URI to match.

With the standard tools installed and `word_count_process` imported, deploy
the example:

```bash
azathoth tool import examples/large-file/tools/sum-results.json
azathoth workflow import examples/large-file/workflows/count-words-in-chunk.json
azathoth workflow import examples/large-file/workflows/count-words-in-large-file.json
azathoth workflow promote a1000000-0000-4000-8000-000000000008
azathoth workflow promote a1000000-0000-4000-8000-000000000009
```

```powershell
azathoth tool import examples/large-file/tools/sum-results.json
azathoth workflow import examples/large-file/workflows/count-words-in-chunk.json
azathoth workflow import examples/large-file/workflows/count-words-in-large-file.json
azathoth workflow promote a1000000-0000-4000-8000-000000000008
azathoth workflow promote a1000000-0000-4000-8000-000000000009
```

The child must be promoted, because a map invokes its production version.
Then send `request.json` to a worker's queue, or run the job directly:

```bash
azathoth job run examples/large-file/request.json
```

```powershell
azathoth job run examples/large-file/request.json
```

The result's `result` holds the file's word count, as `wc -w` counts it.

## How It Is Tested

The tests run the whole example through Azathoth's process runtime against
a stand-in for S3 over HTTP, with a file of three chunks, and check the
count, the chunks and every read. Real S3 meets it in the sandbox
deployment that gates each release.

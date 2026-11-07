# ADR 0117: Citations as Evidence

- Status: Accepted
- Date: 2026-11-07
- Decided in: #142

## Context

A run can be given a document, divide it into segments, and have a model
cite them; every citation is checked with no model involved, and every check
is kept in the content store and recorded as a step's resource (ADR 0112,
ADR 0114, ADR 0116). That evidence ends where the run does.

The parts of Azathoth that judge and improve workflows could not see it.
A benchmark case could not hold a document: a run given a PDF was refused
as a case's source, since a case held only the handle, and how a case would
carry the content was left to this decision (ADR 0112). A benchmark's runs,
and an experiment's, ran with no journal and no content store, so
`segment_pdf` could not read a document in them, and a cited step could not
be shown an extraction or keep its checks.

## Decision

### A case holds a document by its handle and provenance

A benchmark case may name its input's provenance: where the input was read
from, and which content it was, as a run records it in its
`workflow.input.resolved` event (ADR 0112):

```json
{
  "input": {"content": {"digest": "<SHA-256>", "media_type": "application/pdf", "size_bytes": 482113}},
  "input_provenance": {"uri": "file:///claims/claim-0412.pdf", "media_type": "application/pdf", "size_bytes": 482113, "digest": "<SHA-256>"},
  "expected": {"description": "Received.", "value": {"received": "December 14"}, "comparison": "exact"}
}
```

A case whose provenance names a PDF or an image gives exactly that
content's handle as its input:

```text
Benchmark case <CASE_ID> names application/pdf content <DIGEST> as its input provenance, but its input is not that content's handle.
```

The content itself stays in the content store, under its digest, as a run's
does. A case names it; it does not carry it. A case without provenance
serializes without it, so no existing dataset's digest changes, and a case
holding JSON shaped like a handle, with no provenance, is JSON as it always
was.

### A case's run receives its input as its source did

A case's run is given its input, then, when the case names provenance, the
`workflow.input.resolved` event recording it, from the same producer at the
same time. Its tools and prompts read the content by digest, as the run the
case came from did, and anchors name its origin.

### Cases come from runs and from files

`benchmark add-case --from-run` takes a run's input and its provenance. A
run given a PDF or an image, refused before, becomes a case, as long as the
content store still holds the content:

```text
Run <RUN_ID> received content <DIGEST>, which the content store no longer holds.
```

`benchmark add-case --input-file` reads a file as `workflow run
--input-file` does, keeps its content in the store, and makes a case of
what a run given the file would receive, with the file's provenance. It
needs `--expected`, since a file has no feedback.

### Benchmark and experiment runs are runs like any other

The CLI runs every benchmark case, comparison and optimization candidate
with the database's journal and content, as `workflow run` runs a workflow.
`segment_pdf` reads a case's document, a cited step is shown the extractions
a step of the case's run kept, and its checks are kept and recorded. A case
whose content the store no longer holds fails the steps that read it, and
is judged as any failed run is (ADR 0073); the benchmark goes on.

### A case names the segments its run must cite

A case's expected outcome may name a citation expectation: the segments its
run must cite, by the source and segment a cited step names, and whether a
citation that did not verify fails the case:

```json
"expected": {
  "description": "Received on December 14, citing the claim.",
  "value": {"received": "December 14", "citations": [{"source": "claim", "segment": "p1.s2"}]},
  "comparison": "exact",
  "citations": {"require": [{"source": "claim", "segment": "p1.s2"}], "on_unverified": "fail"}
}
```

`on_unverified` is `fail`, the default, or `ignore`. A segment is required
once:

```text
Citation expectation requires segment <SEGMENT> of source '<SOURCE>' more than once.
```

An outcome without an expectation serializes without one, so no existing
dataset's digest changes. `benchmark add-case` names one with
`--require-citation SOURCE:SEGMENT`, repeated for each segment, and
`--on-unverified`.

### Results compare by what they cite

A check's anchor names digests and offsets, and its quote is whatever the
model quoted, so a result citing the right segment in slightly different
words, or a check made against a newer extraction, would never be equal to
the one expected. Before an exact, normalized or semantic comparison, every
citation and every check in either value, an object holding a source, a
segment and a quote and no key a check does not have, compares as
`{source, segment}`. A case judges the answer and what it cited; its
expectation judges whether the citations verified. A schema comparison
validates the result as it is, since a schema may constrain a check's
status.

### What the run cited is read from its records

Whether a case's run met its expectation is read from the checks its cited
steps kept, named by their `citations` resources (ADR 0116), never from the
result, which any later step could have written. A required segment is met
by a verified check, `verified` or `verified_normalized`, of that source and
segment. Under `fail`, any check that did not verify fails the case too;
under `ignore`, only the required segments count.

A case passes only if its outcome passed and its citations did. Its score is
the outcome's score, times the fraction of required segments met and, under
`fail`, the fraction of checks that verified; a case its citations fail
scores below its threshold. Its evaluation keeps the outcome's evidence, and
adds the `citations` evidence the expectation was judged on, and its reason
says how:

```text
The result matched. Citations: 1 of 2 required citations verified; 2 of 3 citations verified. Missing: segment p2.s1 of 'claim'.
```

A record the run's checks cannot be read from fails the case, naming why:

```text
Run <RUN_ID> kept citation records, which cannot be read: it has no content store.
Run <RUN_ID> kept citation record <DIGEST>, which the content store no longer holds.
```

## Consequences

- A benchmark of documents is built the way any benchmark is: from runs
  given them, or from files.
- A case's run sees its document exactly as the run it came from saw it, so
  a benchmark judges a workflow on the documents it was given.
- Every case run of a benchmark, a comparison or an optimization is
  journaled in the database, beside the runs it already recorded.
- A case names its content by digest and is only as portable as the
  content store holding it: a dataset exported to another database needs
  its documents there too.
- ADR 0112's refusal of a run given binary content as a case's source is
  lifted.
- A benchmark can hold a workflow to citing the right segments, and to
  citing nothing that is not there, on the engine's checks alone.
- A case written by hand names citations by their segments, so it does not
  break when a model words a quote differently.

## Alternatives Considered

### Carry the content inside the case

Rejected. A dataset would grow by every document it holds, in every
revision, and the same bytes would be kept twice: once in the store and
once in the dataset. A digest names the content exactly, and the store
already keeps it.

### Judge citations from the result

Rejected. A result is a step's value, and a later step can write
`verified` into it. The records are the engine's own, kept as the check was
made.

### Average a case's outcome and citations

Rejected. A case citing nothing it was asked to, beside a right answer,
would pass on the answer alone at any threshold below 1. A product, held
below the threshold when citations fail, cannot be averaged away.

### Run cases with an in-memory journal

Rejected. A case's run is recorded in the database already; a journal kept
elsewhere would leave `run show` and the content access reading nothing for
it, and a case run's checks unreadable after the benchmark.

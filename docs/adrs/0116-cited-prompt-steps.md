# ADR 0116: Cited Prompt Steps

- Status: Accepted
- Date: 2026-11-07
- Decided in: #141

## Context

A workflow can divide a document into segments and keep them as an
extraction, checked and recorded by the engine (ADR 0114), and a citation of
a segment can be checked against that extraction and anchored to the page and
box it came from (ADR 0113). What lies between is a model: it must be shown
the segments, by the IDs a citation names, and what it cites must be checked
before anything downstream relies on it.

A step bound to an extraction handle is shown the handle today, as JSON:
digests, a tool's name and version, and none of the text. The model has
nothing to cite.

## Decision

### A bound extraction renders as its segments

A template variable whose value is exactly one extraction handle renders the
extraction's segments, in order, each as its ID in brackets and its text,
separated by blank lines, inside a `source` element named by the variable:

```text
<source name="claim">
[p1.s1] Claim 0412.
Filed by the insured.

[p1.s2] Received on December 14.
</source>
```

The variable's name is the source a citation names, and the IDs are the
segments it names. An extraction with no segments renders an empty source.
Any other value renders as it always did: a list of handles, or a handle
with more keys, is JSON. Nothing rendered an extraction handle before, so no
existing prompt changes.

### A prompt renders only extractions its run kept

An extraction is rendered only if a step of the run, or of a run above it in
its lineage, kept it: the engine recorded it as an `extraction` resource of
that step (ADR 0114). The run's journal holds each committed layer's step
runs and their resources, so a later step reads every extraction an earlier
layer kept, whether the run is under way, resumed or finished, and a child
reads its parent's. A handle a step wrote into its own output names nothing
the engine kept, and is refused:

```text
Prompt strategy '<NAME>' shows extraction <DIGEST>, which this run cannot give: it has no content store.
Prompt strategy '<NAME>' shows extraction <DIGEST>, which only a workflow step can give.
Prompt strategy '<NAME>' shows extraction <DIGEST>, which no step of this run kept.
Extraction <DIGEST> is not in the content store.
Prompt strategy '<NAME>' shows extraction <DIGEST>, but its handle does not describe the extraction the content store holds.
```

Content under the digest that is not a segmented text is refused with the
store's own error (ADR 0113). The content access every command builds reads
a run's kept extractions from its journal, beside its initial context.

## Consequences

- A model step can be shown a document's segments by the IDs it may cite,
  with no tool of its own.
- An extraction reaches a prompt only through the engine's record of keeping
  it, so no step can put text in front of a model as a document's.
- Every existing prompt renders as it did.

## Alternatives Considered

### Render the extraction's whole text, without segment IDs

Rejected. A citation names a segment, and a model shown no IDs could only
quote; finding which segment a quote came from would be a guess when it
occurs in two.

### Trust any extraction the content store holds

Rejected. The store holds every extraction every run kept. A handle naming
one this run never made would show a model a document the run was never
given, as though it had been.

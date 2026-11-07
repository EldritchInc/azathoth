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

### A cited step names its policy, and replies in JSON

A context prompt step becomes a cited step by naming a `citations` policy,
which only a step with JSON output may name:

```json
"specification": {
  "template": {"text": "...", "bindings": [...]},
  "model_selection": {...},
  "output_format": "json",
  "citations": {"on_unverified": "fail"}
}
```

```text
Prompt strategy '<NAME>' checks citations, which only a JSON reply holds; its output format is text.
```

A specification without a policy serializes without one, so no existing
document's digest changes.

### A citation is any object of exactly three strings

Wherever in a cited step's reply an object has exactly the keys `source`,
`segment` and `quote`, each a string, it is a citation: of the segment, by
its ID, of the extraction the prompt showed under that source's name. A
reply may cite once or many times, at any depth, so each claim can carry
its own; an object with another key, or a value that is not a string, is
not a citation and is left as it is.

The engine adds nothing to the prompt telling the model how to cite. The
template says, in the author's words, and the whole prompt stays what the
author, or an optimizer, wrote.

### Each citation is checked, and replaced by its check

Each citation is checked against the extraction it names with
`verify_citation` (ADR 0113), with no model involved, and replaced, where it
stood, by its check: the citation as cited, its `status`, and, when its
quote was found, the `anchor` the check built, naming the source's origin
when its input had one. That is the origin an inline input named, or the
URI a reference was read from:

```json
{"source": "claim", "segment": "p1.s2", "quote": "December 14", "status": "verified", "anchor": {"digest": "<SHA-256>", "media_type": "application/pdf", "origin": {"uri": "s3://claims/0412.pdf", "version_id": "<VERSION>"}, "selectors": ["..."], "extraction": {"tool": "segment_pdf", "version": "<VERSION>", "digest": "<SHA-256>"}}}
```

A citation of a source the prompt did not show fails the attempt, whatever
the policy: the reply does not fit its prompt.

```text
Prompt strategy '<NAME>' cites source '<SOURCE>', which its prompt does not show.
```

### Unverified citations fail the attempt, unless they are kept

A quote found exactly is `verified`, and one found only after normalizing is
`verified_normalized`; both are verified. Under `on_unverified` `fail`, the
default, the first citation that is neither fails the attempt, and the
step's retry policy asks the model again:

```text
Prompt strategy '<NAME>' cites '<QUOTE>' from segment <SEGMENT> of source '<SOURCE>', which the segment does not hold.
Prompt strategy '<NAME>' cites segment <SEGMENT> of source '<SOURCE>', which has no such segment.
```

Under `keep`, every check is kept, `quote_not_found` and `unknown_segment`
among them, and the step goes on; what to make of them is a later step's
choice.

### The checks are kept, and recorded as a resource

Every check of a reply, in the order the reply holds them, is kept in the
content store as canonical JSON, `{"checks": [...]}`, and recorded as a
resource of the step: kind `citations`, identified by the record's digest,
with attributes counting the citations and each status. The record is the
engine's, as an extraction's is, so no later step can write `verified` into
a value and have it taken for a check. A run with no content store cannot
keep one, so a cited step there fails:

```text
Prompt strategy '<NAME>' checks citations, which this run cannot keep: it has no content store.
```

## Consequences

- A model step can be shown a document's segments by the IDs it may cite,
  with no tool of its own.
- An extraction reaches a prompt only through the engine's record of keeping
  it, so no step can put text in front of a model as a document's.
- Every existing prompt renders as it did, and every existing specification
  serializes as it did.
- What a cited step cites is checked before any later step reads it, and a
  model that cites what is not there is asked again.
- Every check a run made is in its content store, named by a step's
  resource, and can be checked again from the store alone.

## Alternatives Considered

### Render the extraction's whole text, without segment IDs

Rejected. A citation names a segment, and a model shown no IDs could only
quote; finding which segment a quote came from would be a guess when it
occurs in two.

### Trust any extraction the content store holds

Rejected. The store holds every extraction every run kept. A handle naming
one this run never made would show a model a document the run was never
given, as though it had been.

### Keep only the citations that verified

Rejected. Dropping a citation hides what the model claimed, and a claim
whose support vanished would read as one that never needed any. Under
`keep`, every check stays, with its status.

### Require the citations at one path of the reply

Rejected. A list at a fixed path flattens claims and their support into two
lists a later step must pair again. A citation found wherever it stands
keeps each claim with its own.
